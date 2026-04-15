# CataIEG 归一化结果审查指南

本轮更新重新设计了反应（Reaction）和催化剂（Catalyst）的归一化流程——从字符串匹配改为 LLM 语义归一化 + 二次合并。请协助审查归一化的化学合理性。

本目录提供两个互补的网页工具，用浏览器直接打开即可（不需要启动服务器）。

---

## 环境准备

把本目录（`graph_output/`）下面的文件整个下载到本地，然后：

1. 确保同目录下同时存在这些文件：
   - `case-review.html` + `paper_bundles.json`
   - `edge-explorer.html` + `edge_explorer_data.json`
2. 双击任一 HTML 文件，用 Chrome / Safari / Edge 打开即可
3. 如果浏览器因为安全策略拒绝读取本地 JSON，有两种方法：
   - **推荐**：在 graph_output/ 目录下开个简易 HTTP 服务：
     ```bash
     cd graph_output
     python3 -m http.server 8000
     ```
     然后打开 `http://localhost:8000/case-review.html`
   - 或者用 Firefox，它允许 `file://` 直接读取 JSON

---

## 审查目标

本次归一化有三个核心决策需要化学家把关：

| 决策 | 在哪里看 | 关键问题 |
|---|---|---|
| **催化剂家族合并** | Case Review 侧栏浏览 + Edge Explorer 的 Task 2 | 同一物质是否被正确聚合？不同物质是否被误并？ |
| **反应模板合并** | Case Review 每篇论文的 Reaction 节点 + Edge Explorer 的 Task 1 | 反应是否归到正确的族名？ |
| **跨论文本体共现边** | Edge Explorer 的 Co-occurrence Detail 页 | 预测出的 "反应族 → 材料平台 / 活性位 / 机理标签" 关系是否化学合理？ |

---

## 工具 1：Case Review（逐篇审查）

**`case-review.html`**

### 界面

- **左侧栏**：100 篇论文列表。顶部搜索框可按标题、DOI、催化剂名搜索；左下角的 Prev / Next 按钮或键盘 `←` `→` / `J` `K` 切换论文
- **主内容区**：当前论文的所有图节点，按类型分组折叠
  - Paper → Reaction → Catalyst → Procedure → ProcedureStep → CharacterizationRecord → PerformanceDataset → OperatingPoint → Metric → **MechanisticClaim**（粉色标签）→ **EvidenceItem**（蓝色标签）
- 每个节点卡片显示：节点类型、本地 ID（如 R1, C1, P1）、所有字段、以及与该节点相连的所有边（`EDGES (N)` 段）

### 审查要点

**打开任意一篇论文，重点看 Catalyst 节点：**

对比同一论文内多个 Catalyst 的 `name_reported`，应该符合直觉：例如 Pt(0.1)/Al2O3、Pt(0.3)/Al2O3、Pt(1)/Al2O3 三个催化剂实例，它们指向的 **CatalystFamily 应该是同一个**（通过 `INSTANCE_OF_FAMILY` 边可以追到 family:CFxx 节点，应该是同一个 UID）。

**常见的"要警惕"模式：**

- 同一骨架不同载体比例（如 Pt(0.1)/Al2O3 和 Pt(1)/Al2O3）**应合并**
- 同一沸石骨架不同质子形式（ZSM-5、HZSM-5、nano-ZSM-5）**应合并**
- 带不同金属的载体（Ni/Al2O3 vs NiMo/Al2O3）**不应合并**
- 负载型 vs 裸载体（Pt/Al2O3 vs Al2O3）**不应合并**（这是最容易出错的地方，之前有反馈过）
- 负载型 vs 混合氧化物（Ni/Al2O3 vs NiAl-oxide）**不应合并**

### Reaction 节点审查

同一篇文章内的 Reaction 节点，如果有多个反应（如 R1 是 SMR, R2 是 WGS），归到的 ReactionTemplate 应该不同。如果发现：
- 同一反应被重复建模为多个 Reaction 节点 → 可能是 task1 抽取问题
- 明显是同一反应的 R1、R2 在不同论文里归到不同模板 → 归一化问题

---

## 工具 2：Edge Explorer（边 / 关系审查）

**`edge-explorer.html`**

### 界面

左侧 7 个标签页：

- **Overview**：全局统计。看各任务的边数分布、Top 边类型柱状图
- **Task 1 · Reaction Catalog**：所有反应相关的边，展开每个 edge type 看 3 个示例（`实例 → 实例` 或 `实例 → 本体`）
- **Task 2 · Catalyst Catalog**：催化剂相关
- **Task 3 · Procedure Catalog**：制备流程相关
- **Task 4 · Characterization**：表征相关
- **Task 5 · Performance**：性能数据相关
- **Task 6 · Mechanistic Claims**：机理主张相关
- **Cross-Paper Bridging**：跨论文共现 / 相似 / 共研边
- **Co-occurrence Detail**（最重要）：1582 条本体共现边的完整表格

### Co-occurrence Detail 页——主要审查目标

这是**链接预测任务**的训练 / 评价数据，化学家需要看这些预测的关系是否合理。

工具支持：
- **列排序**：点击表头任何列排序。默认按 `Papers`（跨论文证据数）降序
- **"仅跨论文" 按钮**（右上角）：只显示被 2 篇以上论文共同支持的边（共 631 条），这些是最可靠的关系
- **搜索框**：输入关键词过滤（如 `HZSM` / `dry reforming` / `coke`）
- **点击任一行**：展开显示所有 witness papers（带年份和 DOI 链接）

**三种共现边的含义：**

| 边类型 | 源 → 目标 | 化学意义 |
|---|---|---|
| `LIKELY_USES` | reaction_family → material_platform | "这类反应倾向使用这类材料平台" |
| `LIKELY_ASSOCIATED_WITH` | reaction_family / active_site_form / material_platform → active_site_form / property_name / step_type | "它们在文献中常被放在一起研究" |
| `LIKELY_SUPPORTS` | reaction_family / material_platform / active_site_form / property_name → design_mechanism_tag | "这些上下文支持该机理设计标签" |

**审查步骤（建议）：**

1. 切到 **Co-occurrence Detail**，点 "仅跨论文" 按钮
2. 按 `Papers` 列降序排（默认），先看 top 20 条
3. 对每一条问自己：**"这个关系化学上合理吗？是否常识性事实？"**
   - 合理的例子：`reaction_family:hdo → material_platform:supported_metal_nanoparticles`（跨 14 篇）
   - 合理的例子：`active_site_form:nanoparticle_sites → design_mechanism_tag:coke_resistance_design`（跨 22 篇）
   - 如果遇到不合理的，记下行号 / 源目标 / 反馈回来
4. 点行展开，看 witness papers。如果只跨 2-3 篇论文但听起来很反常，很可能是抽取噪音

**比较推荐的 sanity check 案例：**

- `reaction_family:smr → material_platform:supported_metal_nanoparticles`：SMR 用负载金属催化剂——常识，应该存在
- `reaction_family:dry_reforming → design_mechanism_tag:coke_resistance_design`：干重整与抗积碳——常识，应该存在
- `material_platform:zeolites_molecular_sieves → property_name:conversion`：沸石催化剂报告转化率——常识

---

## 催化剂家族的快速抽查（强烈推荐的第一步）

打开 Edge Explorer → Task 2 → 找到 `INSTANCE_OF_FAMILY` 边，看 3 个示例。然后去 Case Review 里搜对应的家族名。

或者更直接：在 Case Review 里搜索 "HZSM"、"Pt/Al2O3"、"Ni"、"Fe2O3" 等常见家族名，翻看不同论文里被归到同一家族的催化剂，检查是否都合理。

最重要的家族（成员数 > 5）：

| 家族名 | 成员数 | 审查点 |
|---|---|---|
| no_catalyst | 12 | 应该全是空白对照 / 非催化条件 |
| HZSM-5 | 15 | 应该全是 ZSM-5 MFI 骨架（不同硅铝比 / 形貌 OK） |
| NiMo/Al2O3 | 6 | HDS 经典催化剂，应该都是 NiMo 在 γ-Al2O3 上 |
| Ni/Al2O3 | 5 | 不应该混入 NiMo/Al2O3 或纯 Al2O3 |
| Pt/Al2O3 | 5 | 应该是不同 Pt 负载量的 Pt/Al2O3（已核对过） |
| Fe/ZSM-5 | 5 | 应该都是 Fe 负载在 ZSM-5 上，不同载量 |

---

## 附加资源

- `KG-Structure.md`：完整的知识图谱 schema（节点类型、边类型、字段含义）
- `reply-to-collaborators.docx`：对上轮反馈的响应总结（Q1–Q7）
- `nodes.jsonl` / `edges.jsonl`：原始图数据，可用任何工具（jq / Pandas / Neo4j）直接加载
- `catalyst_family_result.json`：每个 Catalyst 的 LLM 归一化结果（name / family / aliases）
- `catalyst_family_dedup_map.json`：二次归一的映射关系（哪些家族被合并到哪些）
- `reaction_template_result.json`：每个 Reaction 的 LLM 归一化结果

如需查看具体的 LLM 提示词：在仓库根目录的 `data/tod/build_graph/` 下，
- `llm_normalize_catalysts.py` 里的 `SYSTEM_PROMPT` 是催化剂归一化规则
- `llm_normalize_reactions.py` 里的 `SYSTEM_PROMPT` 是反应归一化规则
- `llm_dedup_catalyst_families.py` 里的 `SYSTEM_PROMPT` 是家族二次合并规则


