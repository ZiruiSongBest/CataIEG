# 催化证据图构建方案

## 总览

数据源：`sample.jsonl`（100 篇论文，数据丰富）
输出格式：`nodes.jsonl` + `edges.jsonl`（JSON Lines）
核心目标：构建一张包含实例层、本体层、规范化实体层、跨文献桥接层的催化知识图谱

## 整体架构

```
Layer 4: 跨文献桥接层（派生）
    CO_STUDIED_WITH / SIMILAR_TO / COMPARABLE_TO
         ↑ 统计派生
Layer 3: 规范化实体层（归并）
    ReactionTemplate / CatalystFamily
         ↑ INSTANCE_OF
Layer 2: 本体层（映射）
    OntologyTerm (reaction_family, material_platform, ...)
         ↑ IN_FAMILY / HAS_PLATFORM / ...
Layer 1: 实例层（抽取）
    Paper → Reaction / Catalyst / Procedure / Char / Perf
```

---

## Phase 1：实例层构建

### 输入
`sample.jsonl` 中 task0-task5 的结构化数据

### 节点创建

| 节点类型 | 数据来源 | 预估数量 | UID 格式 |
|----------|----------|----------|----------|
| Paper | DOI/title/time | 100 | `paper:<doi_norm>` |
| Reaction | task1.reaction_catalog | ~160 | `reaction:<doi_norm>:R1` |
| Catalyst | task2.catalyst_catalog | ~369 | `catalyst:<doi_norm>:C1` |
| Procedure | task3.procedure_catalog | ~291 | `procedure:<doi_norm>:P1` |
| ProcedureStep | task3.steps | ~801 | `step:<doi_norm>:P1:S1` |
| CharRecord | task4.characterization_records | ~602 | `char:<doi_norm>:CR1` |
| PerfDataset | task5.performance_records | ~309 | `perf:<doi_norm>:PR1` |
| OperatingPoint | task5.operating_points | ~520 | `op:<doi_norm>:PR1:OP1` |
| Metric | task5.metrics_by_catalyst.metrics | ~1654 | `metric:<doi_norm>:PR1:OP1:C1:M1` |

### 边创建

**A. Paper → Instance（文献-实例边）**
- Paper --HAS_REACTION--> Reaction
- Paper --HAS_CATALYST--> Catalyst
- Paper --HAS_PROCEDURE--> Procedure
- Paper --HAS_CHARACTERIZATION--> CharRecord
- Paper --HAS_PERFORMANCE_DATASET--> PerfDataset

**B. Instance → Instance（实例-实例边）**
- Catalyst --TESTED_IN--> Reaction（来自 tested_reaction_ids）
- Procedure --APPLIES_TO--> Catalyst（来自 catalyst_ids）
- Procedure --SPECIFIC_TO--> Reaction（来自 reaction_ids，覆盖率 56.6%）
- Procedure --HAS_STEP--> ProcedureStep
- ProcedureStep --NEXT_STEP--> ProcedureStep（按 step_no 顺序）
- CharRecord --APPLIES_TO_CATALYST--> Catalyst（来自 catalyst_id + applies_to_catalyst_ids）
- CharRecord --LINKED_TO_REACTION--> Reaction（来自 reaction_id，覆盖率 45.7%）
- Reaction --HAS_PERFORMANCE_DATASET--> PerfDataset
- PerfDataset --HAS_OPERATING_POINT--> OperatingPoint
- OperatingPoint --HAS_METRIC--> Metric
- Metric --FOR_CATALYST--> Catalyst
- Metric --UNDER_REACTION--> Reaction

### 处理细节
- DOI 归一化：将 `/` 替换为 `_`，全部小写
- Metric UID：因为原数据没有 M1/M2 ID，按 metrics 数组顺序自动编号
- catalyst_id 字段：CharRecord 中的 catalyst_id 有时是字符串有时是列表，统一处理

---

## Phase 2：本体层构建

### 从实例字段中提取本体节点

遍历所有实例节点，收集每个本体类型字段的所有不同值，每个唯一值创建一个 OntologyTerm 节点：

| 本体类型 (ontology_type) | 数据来源 | 预估种类数 |
|--------------------------|----------|-----------|
| reaction_domain | Reaction.reaction_domain | ~5 |
| reaction_class | Reaction.reaction_class | ~15 |
| reaction_family | Reaction.reaction_family | ~30 |
| material_platform | Catalyst.labels_material_platform | ~17 |
| active_site_form | Catalyst.labels_active_site_form | ~10 |
| morphology_device_form | Catalyst.labels_morphology_device_form | ~12 |
| form_factor | Catalyst.form_factor | ~10 |
| procedure_type | Procedure.procedure_type | ~5 |
| step_type | ProcedureStep.step_type | ~20 |
| method_family | CharRecord.method_family | ~15 |
| sample_state | CharRecord.sample_state | ~6 |
| dataset_type | PerfDataset.dataset_type | ~5 |
| property_name | Metric.property_name | ~20 |
| target_species | Metric.target_species | ~50 |

### 本体映射边

每个实例节点的本体字段值 → 对应的 OntologyTerm 节点建一条映射边：
- Reaction --IN_DOMAIN--> OntologyTerm(reaction_domain)
- Reaction --IN_CLASS--> OntologyTerm(reaction_class)
- Reaction --IN_FAMILY--> OntologyTerm(reaction_family)
- Catalyst --HAS_MATERIAL_PLATFORM--> OntologyTerm(material_platform)
- Catalyst --HAS_ACTIVE_SITE_FORM--> OntologyTerm(active_site_form)
- ...（按 KG-Structure.md 中的完整列表）

---

## Phase 3：规范化实体层构建（解决问题 1：跨文献实体统一）

### 3a. ReactionTemplate

**归并逻辑**：把不同论文中的"同一类反应"归并到同一个模板。

归并 key = `(reaction_family 排序拼接, reactants 归一排序, target_products 归一排序)`

步骤：
1. 对所有 160 个 Reaction 实例，提取 (reaction_family, reactants, target_products)
2. 对 reactants 和 products 做文本归一（小写、去空格、排序）
3. 相同 key 的 Reaction 归为同一个 ReactionTemplate
4. 模板命名取第一个实例的 reaction_name_reported，或从 key 自动生成

输出：
- 节点：`ReactionTemplate`（预估 40-60 个）
- 边：`Reaction --INSTANCE_OF_TEMPLATE--> ReactionTemplate`
- 边：`ReactionTemplate --IN_FAMILY--> OntologyTerm(reaction_family)`

### 3b. CatalystFamily（LLM 辅助归一化）

**归并逻辑**：分两步走。

**Step 1：LLM 组分提取**

对 369 个 catalyst 的 `name_reported`，调用 LLM 提取标准化组分：

```
输入: "5 wt% Ni/CeO₂-rod"
输出: {
  "active_metals": ["Ni"],
  "support": "CeO2",
  "dopants": [],
  "promoters": [],
  "morphology": "rod",
  "canonical_name": "Ni/CeO2"
}
```

这一步需要调用 LLM，可以批量处理（每次传入 20-30 个 name_reported）。

**Step 2：确定性聚类**

用 LLM 输出的 `canonical_name` 作为聚类 key：
- 相同 canonical_name 的 Catalyst 归为同一个 CatalystFamily
- CatalystFamily 节点的属性取自其成员的众数标签

输出：
- 节点：`CatalystFamily`（预估 80-150 个）
- 边：`Catalyst --INSTANCE_OF_FAMILY--> CatalystFamily`
- 边：`CatalystFamily --HAS_MATERIAL_PLATFORM--> OntologyTerm`
- 边：`CatalystFamily --HAS_ACTIVE_SITE_FORM--> OntologyTerm`

### 3c. ProcedureTemplate（可选，Phase 3 后期）

归并 key = `(procedure_type, step_type 序列 排序)`

把步骤类型序列相同的 Procedure 归为同一个模板。

---

## Phase 4：跨文献桥接层构建（解决问题 2：本体共研关系）

### 4a. 本体-本体共现边（CO_STUDIED_WITH）

**计算逻辑**：

遍历每篇 Paper 的实例子图，收集该 Paper 中出现的所有本体标签对。

三种共现粒度：

**Paper 级共现**：同一篇论文中同时出现了 onto_A 和 onto_B
```
例：Paper X 有 Reaction(family=OER) 和 Catalyst(platform=perovskite)
→ CO_STUDIED_WITH(reaction_family:OER, material_platform:perovskite, level=paper, count=1)
```

**Catalyst-Reaction 级共现**：同一个 Catalyst 通过 TESTED_IN 连到的 Reaction 的标签 × 该 Catalyst 自身的标签
```
例：Catalyst C1(platform=perovskite) --TESTED_IN--> Reaction R1(family=OER)
→ CO_STUDIED_WITH(reaction_family:OER, material_platform:perovskite, level=instance, count=1)
```

**有方向的共现对类型**：

| source_type | target_type | 含义 |
|-------------|-------------|------|
| reaction_family | material_platform | 什么反应用什么材料 |
| reaction_family | active_site_form | 什么反应对应什么活性位 |
| material_platform | active_site_form | 什么材料有什么活性位 |
| material_platform | procedure_type | 什么材料用什么制备方法 |
| material_platform | step_type | 什么材料制备涉及什么步骤 |
| reaction_family | property_name | 什么反应关注什么性能 |
| material_platform | method_family | 什么材料常做什么表征 |
| sample_state | method_family | 什么状态用什么方法表征 |
| reaction_family | dataset_type | 什么反应测什么类型性能 |

每条边的属性：
```json
{
  "source_uid": "onto:reaction_family:OER",
  "target_uid": "onto:material_platform:perovskite",
  "edge_type": "CO_STUDIED_WITH",
  "co_occurrence_count": 15,
  "witness_paper_count": 8,
  "witness_papers": ["paper:doi1", "paper:doi2", ...],
  "first_year": 2015,
  "last_year": 2024
}
```

### 4b. 规范化实体间的共研边

在 ReactionTemplate 和 CatalystFamily 之间也建共现边：

- `CatalystFamily --TESTED_IN_TEMPLATE--> ReactionTemplate`
  - 属性：witness_count, witness_papers, first_year, last_year

这是未来 link prediction 的核心训练数据：已有的 (CatalystFamily, ReactionTemplate) 配对 = 正样本。

### 4c. 相似度边（SIMILAR_TO）

**Catalyst SIMILAR_TO Catalyst**（跨论文）：
- 在不同 CatalystFamily 之间，如果 material_platform 和 active_site_form 有重叠，建 SIMILAR_TO
- 同一 CatalystFamily 内部的不同 Catalyst 实例也建 SIMILAR_TO

**Reaction SIMILAR_TO Reaction**（跨论文）：
- 不同 ReactionTemplate 之间，如果 reaction_class 相同或 reactants 有交集，建 SIMILAR_TO

---

## 输出文件规格

### nodes.jsonl

每行一个节点 JSON：

```json
{"uid": "paper:10.1016_j.fuproc.2022.107352", "node_type": "Paper", "doi": "10.1016/j.fuproc.2022.107352", "title": "...", "year": 2022}
{"uid": "reaction:10.1016_j.fuproc.2022.107352:R1", "node_type": "Reaction", "local_id": "R1", "reaction_name_reported": "...", ...}
{"uid": "onto:reaction_family:OER", "node_type": "OntologyTerm", "ontology_type": "reaction_family", "canonical_name": "OER"}
{"uid": "rxn_template:OER_aqueous", "node_type": "ReactionTemplate", "template_name": "...", "instance_count": 15}
{"uid": "cat_family:Ni_CeO2", "node_type": "CatalystFamily", "canonical_name": "Ni/CeO2", "instance_count": 8}
```

### edges.jsonl

每行一条边 JSON：

```json
{"source": "paper:10.1016...", "target": "reaction:10.1016...:R1", "edge_type": "HAS_REACTION"}
{"source": "catalyst:10.1016...:C1", "target": "reaction:10.1016...:R1", "edge_type": "TESTED_IN"}
{"source": "reaction:10.1016...:R1", "target": "onto:reaction_family:selective_oxidation", "edge_type": "IN_FAMILY"}
{"source": "reaction:10.1016...:R1", "target": "rxn_template:CLOCM", "edge_type": "INSTANCE_OF_TEMPLATE"}
{"source": "onto:reaction_family:OER", "target": "onto:material_platform:perovskite", "edge_type": "CO_STUDIED_WITH", "count": 15, "papers": [...]}
```

---

## 代码组织

```
build_graph/
├── config.py              # 路径、常量
├── phase1_instance.py     # 实例层：解析 JSONL → 节点 + 边
├── phase2_ontology.py     # 本体层：提取本体节点 + 映射边
├── phase3a_rxn_template.py   # ReactionTemplate 归并
├── phase3b_cat_family.py     # CatalystFamily LLM 归一化 + 聚类
├── phase4_bridge.py       # 跨文献桥接：共现边 + 相似度边
├── main.py                # 串联所有 phase，输出 nodes.jsonl + edges.jsonl
├── stats.py               # 统计报告：节点/边计数、覆盖率
└── prompts/
    └── catalyst_normalize.txt  # LLM 催化剂归一化 prompt
```

---

## 执行顺序

1. **Phase 1 + 2**（纯规则，无 LLM）：解析数据 → 实例层 + 本体层
   - 预估输出：~4800 节点，~8000 边

2. **Phase 3a**（纯规则）：ReactionTemplate 归并
   - 预估输出：+50 节点，+200 边

3. **Phase 3b**（需要 LLM）：CatalystFamily 归一化
   - 需要 LLM 调用：~15-20 次（每次批量处理 20 个催化剂名称）
   - 预估输出：+120 节点，+500 边

4. **Phase 4**（纯规则）：跨文献桥接
   - 预估输出：+500-1000 CO_STUDIED_WITH 边，+200 SIMILAR_TO 边

**总预估图规模**：~5000 节点，~10000 边

---

## 未覆盖的内容（后续阶段）

- **MechanisticClaim + EvidenceItem**：需要重新 LLM 抽取 task6，不在本次范围内
- **Metric.basis 补全**：5.6% 填充率太低，可能需要后处理
- **500sample.jsonl 扩展**：需要先补 catalyst 标签和 procedure steps
- **ConditionBin / OutcomeLabel**：supplyment.md 中的离散化节点，属于进阶优化
