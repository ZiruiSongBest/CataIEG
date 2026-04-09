# 关于 Reaction / Catalyst 归并方案的回复

## 你们的顾虑我都想过了，说一下我们目前的做法

---

### 1. Reaction 归并："完全一致算同一个"确实不合理，我们没这么做

我们的做法是 **结构化 key 归并**，不是简单的字符串精确匹配。

具体来说，每个 Reaction 节点已经有结构化字段（reaction_domain / reaction_class / reaction_family / reactants / target_products），我们用这些字段组合生成一个归并 key：

- 如果 reactants 和 products 都有值，key = `domain + class + family + reactants(归一化排序) + products(归一化排序)`
- 如果没有 reactants/products，用 transformation 文本的前 120 字符作为兜底

归一化包括：H2/hydrogen/h₂ 统一为 H2，water/steam/H2O 统一为 H2O，等等常见化学物种别名对齐。

目前的效果：160 个 Reaction → 158 个 ReactionTemplate。只有 "dry reforming of methane" 和 "water-gas shift" 各自归并了 2 篇论文的反应。归并率确实很低，原因是 100 篇论文的反应种类本身就很分散。

**关于你说的"让 LLM 统计有多少种然后合并"**——这个思路是对的，而且确实可以作为下一步优化。目前的 158 个模板可以导出给 LLM，让它做二次归并（类似 CatalystFamily 的做法）。但当前阶段，结构化 key 已经足以保证"不会把不同反应错误合并"，宁可漏合并也不错合并。

---

### 2. Catalyst 归并：确实是 LLM 做的，不是人工对齐

你说得对，369 个催化剂名称差异太大，人工对齐不现实。我们的做法正是 **LLM 批量标准化**：

把 369 个催化剂的 name_reported、substrate_or_support、labels_material_platform 等信息打包，分 10 批（每批 40 个）发给 Claude Sonnet 4.6，让它输出 canonical_name。

LLM 的 prompt 里有 16 条归一化规则，比如：
- 去载量（"0.5%Fe/ZSM-5" → "Fe/ZSM-5"）
- 统一载体写法（γ-Al2O3 → Al2O3，silica → SiO2）
- 保留有意义的区分（activated carbon ≠ CNT ≠ graphene，不能笼统归为 "C"）
- 生物催化剂按属+种归类
- 只在载量/形貌/制备细节不同时才合并

效果：369 → 246 个 CatalystFamily，46 个多成员家族。例如：
- "0.5%Fe/ZSM-5", "1%Fe/ZSM-5", "2%Fe/ZSM-5", "4%Fe/ZSM-5", "8%Fe/ZSM-5" → 全部归入 **Fe/ZSM-5**
- "CuZnAl-0.5", "CuZnAl-1.5", "CuZnAl-2.5", "CuZnAl-3.5" → 全部归入 **CuZnAl alloy**
- "HPW/TiO2", "HPW/TiO2 calcined at 150°C/200°C/300°C/400°C" → 全部归入 **HPW/TiO2**

---

### 3. 关于"添加 key，继承对方的连接关系"——我们正是这么做的

架构上我们用了一个 **两层抽象**：

```
Layer 1 (实例层):  Catalyst_A  ──TESTED_IN──>  Reaction_X
                       │                            │
                   INSTANCE_OF_FAMILY          INSTANCE_OF_TEMPLATE
                       │                            │
                       ▼                            ▼
Layer 3 (归并层):  CatalystFamily  ──TESTED_IN_TEMPLATE──>  ReactionTemplate
```

每个 Catalyst 实例通过 `INSTANCE_OF_FAMILY` 边连到它所属的 CatalystFamily，每个 Reaction 实例通过 `INSTANCE_OF_TEMPLATE` 边连到它所属的 ReactionTemplate。

然后在 Phase 4 中，我们自动把实例层的 `Catalyst→TESTED_IN→Reaction` 关系 **提升** 到归并层：如果 CatalystFamily_A 的某个成员催化剂在实例层中 TESTED_IN 了某个 Reaction，而那个 Reaction 属于 ReactionTemplate_B，那就自动生成一条 `CatalystFamily_A → TESTED_IN_TEMPLATE → ReactionTemplate_B` 边。

这样就实现了你说的"继承连接关系"。而且实例层的原始边也全部保留，不会因为归并而丢失信息。

举个具体例子：**HZSM-5** 这个 CatalystFamily 有 13 个成员催化剂，分布在 5 篇不同论文中，参与了 etherification、catalytic cracking、ethanol dehydration、MTH reaction 等多种反应。通过 TESTED_IN_TEMPLATE 边，这些跨论文的关系全部自动聚合到了 CatalystFamily 节点上。

---

### 4. 总结：我们的方案架构

| 问题 | 解决方案 | 效果 |
|------|---------|------|
| Reaction 怎么归并 | 结构化字段组合 key（domain+class+family+reactants+products） | 160 → 158 模板 |
| Catalyst 怎么归并 | LLM (Claude Sonnet 4.6) 批量标准化 canonical_name | 369 → 246 家族 |
| 归并后怎么继承连接 | 两层架构：实例层保持不变，归并层通过 INSTANCE_OF 边连接，Phase 4 自动提升边 | 372 条 TESTED_IN_TEMPLATE 跨文献边 |
| 模糊匹配/相似度 | 在归并层额外建 SIMILAR_TO 边（基于属性重叠） | 860 条相似边 |

整个 pipeline 完全自动化，跑一次 0.6 秒（LLM 归一化额外约 2 分钟），输出 5645 节点 + 26307 条边，零悬挂边零重复边。

**下一步可以做的优化**：把 158 个 ReactionTemplate 也交给 LLM 做二次归并，这样反应侧的归并率也能上来。
