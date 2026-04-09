# 催化证据图构建方案 — Codex 审查指南

## 一、任务背景

用户要求：将 `sample.jsonl`（100 篇多相催化论文的结构化抽取数据）按照 `KG-Structure.md` 定义的 schema，构建一张包含 4 层结构的催化证据知识图谱（Heterogeneous Catalysis Evidence Graph），最终输出 `nodes.jsonl` + `edges.jsonl`。

核心要解决的两个问题（定义在 `new-edge.md` 中）：
1. **跨文献实体统一**：不同论文描述的同一催化剂/反应如何归并？（例如 "5wt%Ni/Al2O3" 和 "Ni/γ-Al2O3" 本质是同一类催化剂）
2. **本体共研关系**：如何从实例层推导出"哪些材料平台常与哪些反应类型共同出现"这种跨文献统计关系？

## 二、实现架构

```
数据源: sample.jsonl (100篇论文, task0-task5结构化数据)
         │
         ▼
    ┌─ Phase 1: 实例层 ── phase1_instance.py
    │   解析 task0-5 → Paper/Reaction/Catalyst/Procedure/
    │   ProcedureStep/CharacterizationRecord/PerformanceDataset/
    │   OperatingPoint/Metric 共 9 类节点 + 实例间边
    │
    ├─ Phase 2: 本体层 ── phase2_ontology.py
    │   从实例字段提取 OntologyTerm 节点 (16种本体类型)
    │   + 实例→本体 映射边
    │
    ├─ Phase 3a: ReactionTemplate ── phase3a_rxn_template.py
    │   按 (domain, class, family) 归并反应实例
    │   160 个 Reaction → 91 个模板
    │
    ├─ Phase 3b: CatalystFamily ── phase3b_cat_family.py
    │                               + llm_normalize_catalysts.py
    │   调用 Claude API 对 369 个催化剂名称做 canonical_name 归一化
    │   369 个 Catalyst → 188 个家族
    │
    └─ Phase 4: 跨文献桥接 ── phase4_bridge.py
        4a: CO_STUDIED_WITH (本体-本体共现，1307条)
        4b: TESTED_IN_TEMPLATE (家族→模板共研，276条)
        4c: SIMILAR_TO (模板/家族间相似度，860条)
         │
         ▼
    main.py 串联 → 去重 + 验证 → nodes.jsonl + edges.jsonl
```

## 三、代码文件清单与职责

```
build_graph/
├── config.py                 (20行)  路径常量, DOI归一化函数
├── main.py                   (139行) 主流程编排, 边去重, 悬挂边验证
├── phase1_instance.py        (229行) 解析task0-5→9类节点+实例间边
├── phase2_ontology.py        (69行)  16种本体类型提取+映射边
├── phase3a_rxn_template.py   (90行)  ReactionTemplate归并
├── phase3b_cat_family.py     (138行) CatalystFamily构建(消费LLM结果)
├── phase4_bridge.py          (247行) CO_STUDIED_WITH/TESTED_IN_TEMPLATE/SIMILAR_TO
├── stats.py                  (102行) 统计报表生成
├── llm_normalize_catalysts.py(197行) 调Claude API做催化剂名称归一化
└── smart_normalize.py        (408行) 纯规则归一化(备选方案)
```

输出文件 (`graph_output/`):
- `nodes.jsonl` — 5520 个节点 (2.0 MB)
- `edges.jsonl` — 23680 条边 (3.6 MB)
- `stats.json` — 统计摘要
- `catalyst_family_result.json` — LLM归一化结果 (369条 uid→canonical_name)
- `catalyst_names_for_llm.json` — LLM输入 (369个催化剂的name/support/platform)

## 四、最终图规模

| 节点类型 | 数量 | 层级 |
|----------|------|------|
| Paper | 100 | 实例层 |
| Reaction | 160 | 实例层 |
| Catalyst | 369 | 实例层 |
| Procedure | 291 | 实例层 |
| ProcedureStep | 801 | 实例层 |
| CharacterizationRecord | 602 | 实例层 |
| PerformanceDataset | 309 | 实例层 |
| OperatingPoint | 520 | 实例层 |
| Metric | 1654 | 实例层 |
| OntologyTerm | 435 | 本体层 |
| ReactionTemplate | 91 | 规范化实体层 |
| CatalystFamily | 188 | 规范化实体层 |
| **总计** | **5520** | |

边类型共 37 种，总计 23680 条。

## 五、Codex 审查要点

### 审查 1: Schema 一致性

**检查 `KG-Structure.md` 中定义的所有节点类型和边类型是否都在代码中实现。**

```bash
# 检查节点类型覆盖
python3 -c "
import json
node_types = set()
with open('graph_output/nodes.jsonl') as f:
    for line in f:
        node_types.add(json.loads(line)['node_type'])
print('实际节点类型:', sorted(node_types))

# Schema定义的节点类型 (KG-Structure.md):
# Paper, Reaction, Catalyst, Procedure, ProcedureStep,
# CharacterizationRecord, PerformanceDataset, OperatingPoint, Metric,
# OntologyTerm, ReactionTemplate, CatalystFamily
# 缺失: MechanisticClaim, EvidenceItem (task6数据为空, 已知缺失)
"
```

**需要确认**:
- 12 种节点类型是否和 KG-Structure.md 一致（除 MechanisticClaim/EvidenceItem 已知缺失外）
- 37 种边类型是否和 KG-Structure.md 定义的完整边类型列表匹配
- UID 格式是否严格遵循 `paper:<doi_norm>`, `reaction:<doi_norm>:R1` 等规范

### 审查 2: 数据完整性

**检查 sample.jsonl 中的所有数据是否都被正确解析进图中。**

```bash
# 验证节点数量与源数据一致
python3 -c "
import json

# 统计源数据
papers = []
with open('sample.jsonl') as f:
    for line in f:
        papers.append(json.loads(line))

n_reactions = sum(len(p.get('task1',{}).get('reaction_catalog',[])) for p in papers)
n_catalysts = sum(len(p.get('task2',{}).get('catalyst_catalog',[])) for p in papers)
n_procedures = sum(len(p.get('task3',{}).get('procedure_catalog',[])) for p in papers)
n_steps = sum(
    len(proc.get('steps',[]))
    for p in papers
    for proc in p.get('task3',{}).get('procedure_catalog',[])
)
n_chars = sum(len(p.get('task4',{}).get('characterization_records',[])) for p in papers)
n_perfs = sum(len(p.get('task5',{}).get('performance_records',[])) for p in papers)

print(f'源数据: papers={len(papers)}, reactions={n_reactions}, catalysts={n_catalysts}')
print(f'  procedures={n_procedures}, steps={n_steps}, chars={n_chars}, perfs={n_perfs}')
print()
print('与 graph_output/stats.json 中的数量对比, 应该完全一致')
"
```

**需要确认**:
- Paper=100, Reaction=160, Catalyst=369, Procedure=291 等数量是否准确
- 每个节点是否保留了 KG-Structure.md 中定义的所有字段（不多不少）
- Metric 的自动编号 (M1, M2...) 逻辑是否正确

### 审查 3: 边的正确性（最重要）

**检查所有边的 source 和 target 是否指向正确类型的节点。**

```bash
# 验证边的 source/target 类型约束
python3 -c "
import json

# 加载所有节点的 uid → node_type 映射
uid_type = {}
with open('graph_output/nodes.jsonl') as f:
    for line in f:
        n = json.loads(line)
        uid_type[n['uid']] = n['node_type']

# 定义期望的 (source_type, target_type) 约束
EDGE_TYPE_CONSTRAINTS = {
    'HAS_REACTION': ('Paper', 'Reaction'),
    'HAS_CATALYST': ('Paper', 'Catalyst'),
    'HAS_PROCEDURE': ('Paper', 'Procedure'),
    'HAS_CHARACTERIZATION': ('Paper', 'CharacterizationRecord'),
    'HAS_PERFORMANCE_DATASET': ('Paper|Reaction', 'PerformanceDataset'),
    'TESTED_IN': ('Catalyst', 'Reaction'),
    'APPLIES_TO': ('Procedure', 'Catalyst'),
    'SPECIFIC_TO': ('Procedure', 'Reaction'),
    'HAS_STEP': ('Procedure', 'ProcedureStep'),
    'NEXT_STEP': ('ProcedureStep', 'ProcedureStep'),
    'APPLIES_TO_CATALYST': ('CharacterizationRecord', 'Catalyst'),
    'LINKED_TO_REACTION': ('CharacterizationRecord', 'Reaction'),
    'HAS_OPERATING_POINT': ('PerformanceDataset', 'OperatingPoint'),
    'HAS_METRIC': ('OperatingPoint', 'Metric'),
    'FOR_CATALYST': ('Metric', 'Catalyst'),
    'UNDER_REACTION': ('Metric', 'Reaction'),
    'INSTANCE_OF_TEMPLATE': ('Reaction', 'ReactionTemplate'),
    'INSTANCE_OF_FAMILY': ('Catalyst', 'CatalystFamily'),
    'TESTED_IN_TEMPLATE': ('CatalystFamily', 'ReactionTemplate'),
    'CO_STUDIED_WITH': ('OntologyTerm', 'OntologyTerm'),
    'SIMILAR_TO': ('ReactionTemplate|CatalystFamily', 'ReactionTemplate|CatalystFamily'),
}

# 检查每条边
violations = []
with open('graph_output/edges.jsonl') as f:
    for line in f:
        e = json.loads(line)
        src_type = uid_type.get(e['source'], 'MISSING')
        tgt_type = uid_type.get(e['target'], 'MISSING')
        if src_type == 'MISSING' or tgt_type == 'MISSING':
            violations.append(f'DANGLING: {e[\"edge_type\"]} {e[\"source\"]} -> {e[\"target\"]}')
            continue

        constraint = EDGE_TYPE_CONSTRAINTS.get(e['edge_type'])
        if constraint:
            valid_src = src_type in constraint[0].split('|')
            valid_tgt = tgt_type in constraint[1].split('|')
            if not valid_src or not valid_tgt:
                violations.append(f'TYPE_MISMATCH: {e[\"edge_type\"]} expects {constraint} but got ({src_type}, {tgt_type})')

if violations:
    print(f'Found {len(violations)} violations:')
    for v in violations[:20]:
        print(f'  {v}')
else:
    print('All edge type constraints passed!')
"
```

**需要确认**:
- 零悬挂边 (所有 source/target 都指向存在的节点)
- 每种边类型的 source 和 target 节点类型符合 schema 约束
- 无重复边（同一 source+target+edge_type 组合不应出现多次）

### 审查 4: Phase 3a ReactionTemplate 归并逻辑

**检查 phase3a_rxn_template.py 中的归并 key 设计。**

```bash
# 查看归并 key 的选择
cat build_graph/phase3a_rxn_template.py | head -50
```

**需要确认**:
- 非 "other" 家族使用 `(domain, class, family)` 作为归并 key — 这是粗粒度但合理的选择
- "other_named_family" 使用 transformation 前 80 字符作为 key — 防止过度合并
- 160 个 Reaction → 91 个 Template 是否合理（HDO=31, SMR=14, FTS=5, WGS=5 等）
- 单例模板有 77 个，是否因为 key 设计仍然太细或数据确实不同

### 审查 5: Phase 3b CatalystFamily LLM 归一化

**检查 llm_normalize_catalysts.py 的 prompt 设计和结果质量。**

```bash
# 查看 LLM 的 system prompt
grep -A 30 'SYSTEM_PROMPT' build_graph/llm_normalize_catalysts.py

# 抽样检查归一化结果
python3 -c "
import json
with open('graph_output/catalyst_family_result.json') as f:
    results = json.load(f)
with open('graph_output/catalyst_names_for_llm.json') as f:
    inputs = json.load(f)

uid_to_input = {c['uid']: c for c in inputs}

# 抽样显示归一化映射
print('=== 抽样: 多成员家族的归并是否合理 ===')
from collections import defaultdict
groups = defaultdict(list)
for r in results:
    groups[r['canonical_name']].append(r['uid'])

for name, uids in sorted(groups.items(), key=lambda x: -len(x[1]))[:10]:
    print(f'\nFamily: {name} ({len(uids)} members)')
    for uid in uids:
        inp = uid_to_input[uid]
        print(f'  {inp[\"name_reported\"]:50s} support={inp.get(\"substrate_or_support\",\"\")}')
"
```

**需要确认**:
- LLM prompt 中的 12 条归一化规则是否合理（去载量、统一载体名、字母排序等）
- 归一化结果中，被合并的催化剂是否确实是同类材料
- 不应该被合并的催化剂是否被错误合并（false positive 检查）
- 188 个家族中 132 个单例（70%）是否合理，还是有遗漏的合并

### 审查 6: Phase 4 桥接边的合理性

**检查 CO_STUDIED_WITH, TESTED_IN_TEMPLATE, SIMILAR_TO 的派生逻辑。**

```bash
# 查看共现对类型的选择
grep -A 30 'MEANINGFUL_PAIRS' build_graph/phase4_bridge.py

# 检查 SIMILAR_TO 的过滤逻辑
grep -A 20 '_COMMON_PLATFORMS' build_graph/phase4_bridge.py
```

**需要确认**:
- CO_STUDIED_WITH 的 14 种 pair_type 是否覆盖了所有有意义的本体对
- CO_STUDIED_WITH 边是否按 paper 级别聚合（不是 instance 级别）
- SIMILAR_TO 是否排除了过于笼统的 platform（如 supported_metal_nanoparticles）
- TESTED_IN_TEMPLATE 是否正确地将 Catalyst→Reaction 关系提升到 Family→Template 级别

### 审查 7: UID 全局唯一性

```bash
# 检查 UID 是否全局唯一
python3 -c "
import json
from collections import Counter
uids = []
with open('graph_output/nodes.jsonl') as f:
    for line in f:
        uids.append(json.loads(line)['uid'])
dupes = [uid for uid, c in Counter(uids).items() if c > 1]
print(f'Total UIDs: {len(uids)}, Unique: {len(set(uids))}, Duplicates: {len(dupes)}')
if dupes:
    print('Duplicate UIDs:')
    for d in dupes[:10]:
        print(f'  {d}')
"
```

### 审查 8: 已知缺失与局限

以下是**已知的、有意为之的缺失**，不应视为 bug：

1. **MechanisticClaim / EvidenceItem 节点**：task6 数据在 sample.jsonl 中完全为空，无法构建
2. **Metric.basis 字段**：填充率仅 5.6%，对应 TESTS_UNDER_BASIS 边只有 84 条
3. **ProcedureTemplate 节点**：build-plan.md 中标注为"可选，后期"，本次未实现
4. **500sample.jsonl 未使用**：因为数据质量差（缺 catalyst labels 和 procedure steps），改用 sample.jsonl

### 快速验证命令（一键跑完所有检查）

```bash
cd /path/to/AI4Chem/data/tod/build_graph
python3 main.py  # 重新构建图（幂等操作, ~0.5秒）

# 然后运行以下验证
python3 -c "
import json
from collections import Counter

print('=== 1. 加载图数据 ===')
nodes = []
with open('../graph_output/nodes.jsonl') as f:
    for line in f: nodes.append(json.loads(line))
edges = []
with open('../graph_output/edges.jsonl') as f:
    for line in f: edges.append(json.loads(line))
print(f'Nodes: {len(nodes)}, Edges: {len(edges)}')

print('\n=== 2. UID 唯一性 ===')
uids = [n['uid'] for n in nodes]
dupes = len(uids) - len(set(uids))
print(f'Duplicate UIDs: {dupes}')

print('\n=== 3. 悬挂边检查 ===')
uid_set = set(uids)
dangling = sum(1 for e in edges if e['source'] not in uid_set or e['target'] not in uid_set)
print(f'Dangling edges: {dangling}')

print('\n=== 4. 重复边检查 ===')
edge_keys = [(e['source'], e['target'], e['edge_type']) for e in edges]
dupe_edges = len(edge_keys) - len(set(edge_keys))
print(f'Duplicate edges: {dupe_edges}')

print('\n=== 5. 节点类型分布 ===')
type_counts = Counter(n['node_type'] for n in nodes)
for t, c in type_counts.most_common():
    print(f'  {t}: {c}')

print('\n=== 6. 边类型分布 ===')
edge_type_counts = Counter(e['edge_type'] for e in edges)
for t, c in edge_type_counts.most_common():
    print(f'  {t}: {c}')

print('\n=== 7. 源数据 vs 图数据数量对比 ===')
papers = []
with open('../sample.jsonl') as f:
    for line in f: papers.append(json.loads(line))
src_reactions = sum(len(p.get('task1',{}).get('reaction_catalog',[])) for p in papers)
src_catalysts = sum(len(p.get('task2',{}).get('catalyst_catalog',[])) for p in papers)
src_procedures = sum(len(p.get('task3',{}).get('procedure_catalog',[])) for p in papers)
src_chars = sum(len(p.get('task4',{}).get('characterization_records',[])) for p in papers)
src_perfs = sum(len(p.get('task5',{}).get('performance_records',[])) for p in papers)
print(f'  Papers:     src={len(papers):4d}  graph={type_counts[\"Paper\"]:4d}  match={len(papers)==type_counts[\"Paper\"]}')
print(f'  Reactions:  src={src_reactions:4d}  graph={type_counts[\"Reaction\"]:4d}  match={src_reactions==type_counts[\"Reaction\"]}')
print(f'  Catalysts:  src={src_catalysts:4d}  graph={type_counts[\"Catalyst\"]:4d}  match={src_catalysts==type_counts[\"Catalyst\"]}')
print(f'  Procedures: src={src_procedures:4d}  graph={type_counts[\"Procedure\"]:4d}  match={src_procedures==type_counts[\"Procedure\"]}')
print(f'  CharRecs:   src={src_chars:4d}  graph={type_counts[\"CharacterizationRecord\"]:4d}  match={src_chars==type_counts[\"CharacterizationRecord\"]}')
print(f'  PerfRecs:   src={src_perfs:4d}  graph={type_counts[\"PerformanceDataset\"]:4d}  match={src_perfs==type_counts[\"PerformanceDataset\"]}')

print('\n=== All checks done ===')
"
```
