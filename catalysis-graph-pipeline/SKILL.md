---
name: catalysis-graph-pipeline
description: 从已提取的 task0–task6 JSONL 数据批量构建催化证据图（Heterogeneous Catalysis Evidence Graph），包含 LLM 反应/催化剂归一化、跨论文桥接、本体共现预测边，以及 Case Review + Edge Explorer 可视化。当用户提供 sample_6_task.jsonl 格式数据（含 task0..task6 字段），或需要从 catalysis-evidence-graph 的结构化输出构建图、做链接预测数据、或扩大规模（100 → 150k 论文）时，启用本 skill。
---

# Catalysis Evidence Graph Pipeline

从已结构化的催化论文数据批量构建证据图。输入是 `sample_6_task.jsonl`（由 `catalysis-evidence-graph` skill 或同等工具产出），输出是 `nodes.jsonl` + `edges.jsonl` + 两套浏览器可视化。

## When to use

- 用户有 `sample_6_task.jsonl` 或同结构的文件，想构建 / 重建知识图
- 需要跨论文做催化剂家族、反应模板的归一化
- 需要生成本体共现边（`LIKELY_USES` / `LIKELY_ASSOCIATED_WITH` / `LIKELY_SUPPORTS`）作为链接预测的数据
- 需要把 100 规模验证过的流程扩展到 15k / 150k 论文规模

## Inputs expected

每行一条 JSON 论文记录，至少包含：

```json
{
  "DOI": "10.1016/...",
  "title": "...",
  "time": [2020, ...],
  "task1": {"reaction_catalog": [...]},
  "task2": {"catalyst_catalog": [...]},
  "task3": {"procedure_catalog": [...]},
  "task4": {"characterization_records": [...]},
  "task5": {"performance_records": [...]},
  "task6": {"mechanistic_claims": [...]}
}
```

字段细节见 `references/kg-structure.md`。

## Quickstart (single-shard, recommended for < 5k papers)

```bash
export BLTCY_API_KEY=sk-...
export GRAPH_INPUT_FILE=/path/to/sample_6_task.jsonl
export GRAPH_OUTPUT_DIR=/path/to/graph_output
export LLM_CONCURRENCY=8          # 并行 LLM worker 数

bash scripts/run_pipeline.sh
```

流水线会依次完成：

1. **Phase 1 实例层**：解析 task1–task6，生成 Paper / Reaction / Catalyst / Procedure / ProcedureStep / CharacterizationRecord / PerformanceDataset / OperatingPoint / Metric / MechanisticClaim / EvidenceItem 节点和基础边
2. **Phase 2 本体层**：抽取 OntologyTerm（reaction_family, material_platform, active_site_form, property_name, step_type, claim_type, design_mechanism_tag, evidence_type 等）及映射边
3. **LLM 反应归一化** → `canonical_reaction_name` + aliases（`llm_normalize_reactions.py`）
4. **LLM 催化剂归一化** → `canonical_catalyst_name` + `canonical_catalyst_family` + aliases（`llm_normalize_catalysts.py`）
5. **Family 二次归一** → 合并首轮 batch 间粒度不一致的家族（`llm_dedup_catalyst_families.py`）
6. **Phase 3/4 桥接层**：ReactionTemplate、CatalystFamily、TESTED_IN_TEMPLATE、SIMILAR_TO、本体共现有向边（白名单 7 种配对）
7. **可视化数据生成**：`paper_bundles.json`（case-review）+ `edge_explorer_data.json`（edge-explorer）
8. **Publish viz**：把两个 HTML 拷到 output dir，浏览器直接打开即可

输出结构：
```
graph_output/
├── nodes.jsonl
├── edges.jsonl
├── stats.json
├── catalyst_names_for_llm.json            # LLM 输入中间
├── catalyst_family_result.json            # LLM 归一化结果（含 family、name、aliases）
├── catalyst_family_dedup_map.json         # 二次归一映射
├── catalyst_family_result_before_dedup.json  # 备份
├── reaction_names_for_llm.json
├── reaction_template_result.json
├── paper_bundles.json                     # case-review.html 的数据
├── edge_explorer_data.json                # edge-explorer.html 的数据
├── case-review.html
└── edge-explorer.html
```

## Scaling to 15k / 150k papers (sharded)

直接单进程跑 150k 会遇到：LLM 请求总量大、单次失败回退代价高、中间 JSON 过大。用分片运行：

```bash
export BLTCY_API_KEY=sk-...
export LLM_CONCURRENCY=16

python3 scripts/run_sharded.py \
  --input  /data/all_papers.jsonl \
  --outdir /data/graph_runs/run01 \
  --shard-size 1000 \
  --shard-workers 4
```

参数建议见 `references/scaling-guide.md`。核心思路：

- 输入切成 ~1000 篇/分片
- 每分片独立跑完整流水线（LLM + 图构建）
- 分片之间并行（`--shard-workers 4`），每个分片内部 LLM 仍用 `LLM_CONCURRENCY` 并发
- 最后 `run_sharded.py` 把所有分片的 `nodes.jsonl` / `edges.jsonl` 合并，节点按 UID 去重

### 跨分片全局归一化（可选，推荐）

分片内生成的 ReactionTemplate 和 CatalystFamily 是局部的。要得到全局家族，再跑一次 dedup：

```bash
# 把所有分片的 catalyst_family_result.json 合并后
GRAPH_OUTPUT_DIR=/data/graph_runs/run01/graph_output \
  python3 scripts/build_graph/llm_dedup_catalyst_families.py

# 然后重建（不走 LLM，只跑 phase3/4）
GRAPH_OUTPUT_DIR=/data/graph_runs/run01/graph_output \
  python3 scripts/build_graph/main.py
```

## Configuration (env vars)

| Env var | Default | Description |
|---|---|---|
| `GRAPH_INPUT_FILE` | `<skill_root>/sample_6_task.jsonl` | 输入 JSONL |
| `GRAPH_OUTPUT_DIR` | `<skill_root>/graph_output` | 输出目录 |
| `BLTCY_API_KEY` | — | LLM API key（必需）|
| `LLM_BASE_URL` | `https://api.bltcy.ai/v1` | LLM API 根 |
| `LLM_MODEL` | `claude-sonnet-4-6` | 模型 |
| `LLM_CONCURRENCY` | `8` | 并行请求数（每个 Python 进程内）|
| `LLM_MAX_TOKENS` | `4096` | 单次响应 token |
| `LLM_TIMEOUT` | `180` | 秒 |
| `CATALYST_BATCH_SIZE` | `20` | 催化剂每批数 |
| `REACTION_BATCH_SIZE` | `20` | 反应每批数 |
| `DEDUP_BATCH_SIZE` | `120` | family 二次归一每批数 |

## Flags for partial runs

```bash
bash scripts/run_pipeline.sh --skip-llm-reactions    # 只用字符串匹配合并反应
bash scripts/run_pipeline.sh --skip-llm-catalysts    # 只用规则归一催化剂
bash scripts/run_pipeline.sh --skip-dedup            # 跳过 family 二次归一
bash scripts/run_pipeline.sh --viz-only              # 只重建可视化数据
```

## Visualization

两个浏览器端的 HTML，打开对应的 JSON 数据就能用：

- **`case-review.html`**：按论文逐条浏览。左侧论文列表 + 搜索，右侧节点按类型分组（Paper / Reaction / Catalyst / Procedure / ProcedureStep / CharacterizationRecord / PerformanceDataset / OperatingPoint / Metric / **MechanisticClaim** / **EvidenceItem**）。方向键 / J-K 翻页。
- **`edge-explorer.html`**：按 6 个任务类别 + Cross-Paper Bridging 浏览所有边类型。Co-occurrence Detail 页支持按 witness_paper_count 排序、筛选仅跨论文、点击展开 witness papers（带 DOI 链接）。

## Pitfalls

1. **LLM 没设 API key** → 流水线会用字符串匹配 fallback，结果精度会差。必须 `export BLTCY_API_KEY=...`。
2. **Family 二次归一必须在首轮之后**。首轮用 batch 归一化，同一物质在不同 batch 可能被归到不同粒度（HZSM-5 / ZSM-5 / zeolite），二次归一把全部 family 名字送给 LLM 做一次性合并。
3. **本体共现边是实例级别的，不是 paper-level**。即使一篇论文同时研究 R1/R2/C1/C2，只有通过 TESTED_IN 真正配对的 (C, R) 才产生上下文。见 `references/kg-structure.md` 的共现设计。
4. **白名单 7 种有向对**。只有下列配对会生成共现边：
   - `reaction_family → material_platform` (LIKELY_USES)
   - `reaction_family → active_site_form` (LIKELY_ASSOCIATED_WITH)
   - `active_site_form / material_platform → property_name` (LIKELY_ASSOCIATED_WITH)
   - `reaction_family / material_platform / active_site_form → step_type` (LIKELY_ASSOCIATED_WITH)
   - `reaction_family / active_site_form / material_platform / property_name → design_mechanism_tag` (LIKELY_SUPPORTS)
5. **150k 规模的 LLM 成本**：估算 ~600k catalyst + ~150k reaction 条目 → 约 75k LLM batch calls。按 BATCH_SIZE=20, CONCURRENCY=16 并行，每个分片 1000 篇约 20–30 分钟；150 分片可在多机 / 持续运行几天内完成。

## File layout

```
catalysis-graph-pipeline/
├── SKILL.md
├── scripts/
│   ├── run_pipeline.sh               # 单分片端到端
│   ├── run_sharded.py                # 大规模分片运行
│   ├── build_graph/
│   │   ├── config.py                 # 路径/常量 (env-var 可配)
│   │   ├── llm_client.py             # 并行 LLM 客户端
│   │   ├── llm_normalize_reactions.py
│   │   ├── llm_normalize_catalysts.py
│   │   ├── llm_dedup_catalyst_families.py
│   │   ├── phase1_instance.py        # task0..task6 → 实例节点/边
│   │   ├── phase2_ontology.py        # OntologyTerm
│   │   ├── phase3a_rxn_template.py   # ReactionTemplate (LLM)
│   │   ├── phase3b_cat_family.py     # CatalystFamily (LLM + guards)
│   │   ├── phase4_bridge.py          # 跨论文共现、相似度、共研
│   │   ├── stats.py
│   │   └── main.py
│   └── visualize/
│       ├── gen_case_review_data.py
│       ├── gen_edge_explorer_data.py
│       └── publish_viz.sh
├── assets/
│   ├── case-review.html
│   └── edge-explorer.html
└── references/
    ├── kg-structure.md               # 完整 schema
    └── scaling-guide.md              # 150k 规模的调参建议
```
