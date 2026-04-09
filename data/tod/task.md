# 预测任务

反应-材料-制备处理流程-表征结果-催化性能-机理

分成两类：包不包含实例层

1. 先做本底层预测任务，本底层连接只做一个模型，连接时不分逻辑
2. 根据本体曾预测结果，做包含实例层的任务，具体研究方向预测

如何判断本体层连接是否已被研究

### A. 本体层-本体层

“**什么类型的东西会和什么类型的东西在未来形成新联系**”，研究趋势预测。

### 1）反应类型 → 催化材料类型（二元组）

- 目标边：`Onto(reaction_family) --LIKELY_USES--> Onto(material_platform)`
- 含义：预测某类反应未来可能会重点探索什么材料平台
例如：某 reaction family 未来会更多连接到 perovskite、single-atom、MOF-derived、oxide-supported metal 之类的平台

### 2）反应类型 → 活性位形式（二元组）

- 目标边：`Onto(reaction_family) --LIKELY_ASSOCIATED_WITH--> Onto(active_site_form)`
- 含义：预测某类反应未来可能偏向什么活性位设计
如 isolated metal site、dual-site、oxygen vacancy、metal-support interface 等

### 3）反应类型 / 活性位形式 → 机理标签（二元组）

- 目标边：`Onto(reaction_family) --LIKELY_EXPLAINED_BY--> Onto(design_mechanism_tag)`
    
    `Onto(active_site_form) --LIKELY_SUPPORTS--> Onto(design_mechanism_tag)`
    
- 含义：预测未来的机理解释框架，理论叙事方向

### 4）反应类型 ↔ 活性位类型 / 材料平台 ↔ 制备流程类型（三元组）

- 目标边：`Onto(reaction_family, material_platform/active_site_form) --LIKELY_ASSOCIATED_WITH--> Onto(step_type)`
- 含义：某类催化剂用于某类反应更常对应calcination、reduction、etching、ion exchange、activation前处理等
- `Onto(material_platform/active_site_form)` 当作同一类节点
- `reaction_family, material_platform` 有已有边或者新边的情况下，同时与`step_type` 产生边

### 5）活性位类型 / 材料平台 ↔ 反应类型 ↔机理标签（三元组）

- 目标边：`Onto(reaction_family, material_platform) --LIKELY_ASSOCIATED_WITH--> Onto(design_mechanism_tag)`
- 含义：某种设计理念更可能在哪些反应、哪些位点形式中出现
- `Onto(material_platform/active_site_form)` 当作同一类节点
- `reaction_family, material_platform` 有已有边或者新边的情况下，同时与design_mechanism_tag 产生边

---

### B. 本体层-实例层   或  实例层-实例层任务 （每一个任务一个模型）

把**具体实例**和**抽象概念**连接起来，最适合做“给一个具体催化剂/反应推荐研究方向”

### 6）Catalyst 实例 ↔ Reaction实例 / reaction_family 本体（二元组）

- Reaction实例 / reaction_family 本体当作同一类节点
- 含义：某个具体催化剂实例未来最可能被拓展到哪类反应家族

### 7）Catalyst 实例 ↔ Reaction实例 / reaction_family 本体 ↔  active_site_form / design_mechanism_tag / step_type本体（三元组）

- Reaction实例 / reaction_family 本体当作同一类节点；active_site_form本体 / design_mechanism_tag 本体/ step_type当作同一类节点
- Catalyst 、 Reaction有已有边 或者新边的情况下，同时与design_mechanism_tag等本体节点 产生边
- 含义：给具体反应的催化剂推荐它可能对应的活性位认识、设计逻辑、处理流程

---

[KG优化](https://www.notion.so/KG-339ce1b4a20e80269169cfa4b26b7849?pvs=21)

---

### B. 第二重要：规范化实体层预测

这部分比纯本体层更接近真实科研对象，但又比 paper-local instance 更可泛化。我建议你把它作为主战场。

### 6）反应模板 → 催化剂家族

- 目标边：`ReactionTemplate --CANDIDATE_FOR--> CatalystFamily`
- 层次：**规范化实体层 ↔ 规范化实体层**
- 含义：预测某一类标准化反应模板，未来可能出现哪些新的催化剂家族
- 这是最像“发现新方向”的任务

这里特别注意：

不要直接预测 `Reaction instance ↔ Catalyst instance`，而是预测：

- `ReactionTemplate`：跨文献归一后的反应模板
- `CatalystFamily`：跨文献归一后的催化剂家族

### 7）催化剂家族 → 制备模板

- 目标边：`CatalystFamily --LIKELY_PREPARED_BY--> ProcedureTemplate`
- 层次：**规范化实体层 ↔ 规范化实体层**
- 含义：预测某一类催化剂更可能采用什么制备路线
- 可直接服务于实验设计

### 8）催化剂家族 → 表征观察类型

- 目标边：`CatalystFamily --LIKELY_EXHIBITS--> ObservationType`
- 层次：**规范化实体层 ↔ 规范化实体层/本体层**
- 含义：预测某类催化剂常出现哪些关键表征现象
如“高分散”“氧空位富集”“金属-载体强相互作用”

### 9）反应模板 + 催化剂家族 → 机理主张

- 目标：预测一个**三元事实**里的缺失槽位`(ReactionTemplate, CatalystFamily, ?) -> ClaimTheme`
- 层次：**规范化实体层多元预测**
- 含义：在某反应-催化剂组合下，未来最可能被提出的机理解释是什么

这类任务比简单二元边更接近真实科学推理。

---

### C. 后期最有价值：三元/四元/五元事实预测

你已经明确说了想做新的二元组、三元组、四元组、五元组关系预测。这里我建议不要把它理解成“预测很多条链式边”，而要理解成**预测一个高阶事实中的缺失角色**。n-ary KG 研究本身就是为这种问题服务的。

### 10）三元任务

建议重点做这几类：

**T3-1**

- `(reaction_family, material_platform, ?) -> active_site_form`
- 全部偏本体层
- 意义：某类反应 + 某类材料平台，未来会走向什么活性位设计

**T3-2**

- `(ReactionTemplate, CatalystFamily, ?) -> ProcedureTemplate`
- 规范化实体层
- 意义：给某个反应-催化剂候选推荐制备方案

**T3-3**

- `(ReactionTemplate, CatalystFamily, ?) -> ClaimTheme`
- 规范化实体层
- 意义：预测最可能形成的新机理方向

### 11）四元任务

**T4-1**

- `(reaction_family, material_platform, active_site_form, ?) -> claim_type`
- 本体层
- 意义：预测“设计—结构—机理”的组合模式

**T4-2**

- `(ReactionTemplate, CatalystFamily, ProcedureTemplate, ?) -> ObservationType`
- 规范化实体层
- 意义：预测某种制备方案下可能出现的关键结构特征

**T4-3**

- `(ReactionTemplate, CatalystFamily, ClaimTheme, ?) -> MethodFamily`
- 混合层
- 意义：推荐验证该机理最值得做的表征方法

### 12）五元任务

**T5-1**

- `(ReactionTemplate, CatalystFamily, ProcedureTemplate, ObservationType, ?) -> ClaimTheme`
- 含义：给定反应、催化剂家族、制备路线、观察到的关键现象，预测最可能形成的机理主张

**T5-2**

- `(reaction_family, material_platform, active_site_form, step_type_sequence, ?) -> design_mechanism_tag`
- 偏本体/模板层
- 含义：预测一整套“反应—材料—位点—工艺”组合最终会导向哪类设计逻辑

这类五元任务最接近“科研假说生成”。

第一类是**直接二元边预测**，最适合做标准 link prediction。

第二类是**高阶关系预测**，但在你现在“不建预测层”的前提下，不建议把三元组/四元组/五元组当成单独节点去预测，而是把它们定义为**一个小子图（motif）的联合补全任务**。

也就是说：

- **二元组**：直接预测一条新边
- **三元组**：预测两条或三条相关边同时成立
- **四元组 / 五元组**：预测一个局部结构是否闭合

这样最贴合你当前 schema。

---

# 一、最值得优先做的预测任务

## 任务 1：新催化剂–反应配对预测

### 目标边

- `Catalyst --TESTED_IN--> Reaction`

### 对应科学问题

“这个催化剂还没被用于这个反应，但是否值得去做？”

这是最核心、最直接的**新研究方向生成任务**。

本质上就是找新的二元组：

- `(Catalyst, Reaction)`

### 为什么优先

因为它最接近实验决策：

“拿什么材料去做什么反应”。

### 现有图谱还需要补的边

要把这个任务做好，光靠本体边不够，建议再构建：

- `Catalyst --SIMILAR_TO--> Catalyst`
用于跨文献材料迁移。相似性可基于：
    - `labels_material_platform`
    - `labels_active_site_form`
    - `substrate_or_support`
    - `form_factor`
    - 名称规则归一化后的组分相似
- `Reaction --SIMILAR_TO--> Reaction`
用于跨反应迁移。相似性可基于：
    - `reaction_domain`
    - `reaction_class`
    - `reaction_family`
    - reactants / target_products 重叠
- `Catalyst --OUTPERFORMS--> Catalyst`
这是一个很有价值的**派生边**。
在同一 `Reaction + OperatingPoint + property_name` 下，如果 C1 的性能显著优于 C2，就建这条边。
它会让“哪些催化剂家族在某类反应里普遍更强”更容易学出来。

---

## 任务 2：新流程–催化剂适配预测

### 目标边

- `Procedure --APPLIES_TO--> Catalyst`

### 对应科学问题

“这个制备/活化/预处理流程，是否可以迁移到一个新的催化剂体系上？”

这是很重要的**工艺迁移任务**。

对应新的二元组：

- `(Procedure, Catalyst)`

### 研究价值

很多新方向并不是“新材料”，而是“旧材料 + 新处理流程”。

比如某种活化方式、还原方式、重构方式，能否迁移到相似材料上。

### 现有图谱还需要补的边

建议增加：

- `Procedure --SIMILAR_TO--> Procedure`
相似性可基于：
    - `procedure_type`
    - step 序列
    - `step_type` 分布
    - 关键参数模式（温度、气氛、时间）
- `Procedure --YIELDS_SAMPLE_STATE--> OntologyTerm(sample_state)`
    
    这个边很重要。
    
    因为很多 procedure 的真正作用不是“做了一个流程”，而是“把样品带到了某种状态”，比如：
    
    - activated_pretreated
    - reduced
    - sulfided
    - spent_after_reaction
    - reconstructed_surface
    
    你现在有 `CharacterizationRecord.sample_state`，也有 `Metric.catalyst_state_during_test`，但**Procedure 和 state 还没有显式连起来**。这条边补上以后，流程迁移会更可学。
    
- `Catalyst --SIMILAR_TO--> Catalyst`
这个和任务 1 共用。

---

## 任务 3：新流程–反应适配预测

### 目标边

- `Procedure --SPECIFIC_TO--> Reaction`

### 对应科学问题

“这种制备/活化/再生流程，是否适合这个反应体系？”

对应新的二元组：

- `(Procedure, Reaction)`

### 研究价值

有些流程不是针对某种具体材料，而是针对某类反应的通用要求。

比如某类 reaction family 往往需要某种预处理状态、某种活化环境、某种再生流程。

### 现有图谱还需要补的边

建议增加：

- `Reaction --REQUIRES_SAMPLE_STATE--> OntologyTerm(sample_state)`
表示某类反应往往依赖某种样品状态。
这不是原始抽取边，而是从已有数据归纳出来的**规范化边**。
- `Procedure --YIELDS_SAMPLE_STATE--> OntologyTerm(sample_state)`
和上面形成桥接。
- `Reaction --SIMILAR_TO--> Reaction`
- `Procedure --SIMILAR_TO--> Procedure`

这样模型才能学到：

“某流程能产出某状态，而某反应偏好该状态，所以该流程可能适用于该反应”。

---

## 任务 4：性能子图补全任务

这类任务不是单纯一条边，而是最值得做的**三元组/四元组/五元组任务**来源。

### 目标子图

你现有 schema 里，性能不是一个简单边，而是：

- `Reaction --HAS_PERFORMANCE_DATASET--> PerformanceDataset`
- `PerformanceDataset --HAS_OPERATING_POINT--> OperatingPoint`
- `OperatingPoint --HAS_METRIC--> Metric`
- `Metric --FOR_CATALYST--> Catalyst`
- `Metric --UNDER_REACTION--> Reaction`
- `Metric --TESTS_PROPERTY--> OntologyTerm(property_name)`

所以高阶关系最好定义为：

### 4.1 三元组任务

预测：

- `(Catalyst, Reaction, property_name)`

在图里对应为：

是否存在某个 `Metric`，同时满足：

- `Metric --FOR_CATALYST--> Catalyst`
- `Metric --UNDER_REACTION--> Reaction`
- `Metric --TESTS_PROPERTY--> property_name`

### 4.2 四元组任务

预测：

- `(Catalyst, Reaction, OperatingPoint, property_name)`

在图里对应为：

是否存在某个 `Metric`，并被某个 `OperatingPoint` 挂载。

### 4.3 五元组任务

预测：

- `(Catalyst, Procedure, Reaction, OperatingPoint, property_name)`

在图里对应为：

1. `Procedure --APPLIES_TO--> Catalyst`
2. `Procedure --SPECIFIC_TO--> Reaction`
3. 存在某个 `Metric`，连到 `Catalyst + Reaction + property_name`
4. 该 `Metric` 属于某个 `OperatingPoint`

这就是你最有价值的“五元组研究方向”任务。

它表达的是：

**某催化剂在某流程处理后，在某反应、某条件下，是否可能表现出目标性质。**

### 现有图谱还需要补的边

为支持这个性能子图补全，建议新增：

- `OperatingPoint --COMPARABLE_TO--> OperatingPoint`
因为不同 paper 的 OP 只有在条件可比时才能迁移学习。
这是跨文献性能预测非常关键的一条边。
- `Metric --UNDER_SAMPLE_STATE--> OntologyTerm(sample_state)`
目前 `Metric` 里有 `catalyst_state_during_test`，但还是文本属性。
最好把它显式映射成边，这样“状态–性能”关系才能进入图学习。
- `Procedure --ASSOCIATED_WITH_METRIC--> Metric`
表示这个 metric 对应的样品来自哪个流程。
否则 procedure 和 performance 之间要绕很远的路径，模型不容易直接学到“流程影响性能”。
- `CharacterizationRecord --ASSOCIATED_WITH_METRIC--> Metric`
这条边很重要。
它把“结构/状态表征”和“性能结果”直接桥接起来，是后续做 structure–performance 学习的核心。
- `Metric --BETTER_THAN--> Metric`
在可比条件下建立 pairwise ranking。
这对“推荐更优候选”非常有用。

---

## 任务 5：机理迁移预测

### 目标边

- `MechanisticClaim --APPLIES_TO_CATALYST--> Catalyst`
- `MechanisticClaim --ABOUT_REACTION--> Reaction`

### 对应科学问题

“这个机理主张，是否也适用于新的催化剂或新的反应体系？”

对应新的二元组或三元组：

- `(MechanisticClaim, Catalyst)`
- `(MechanisticClaim, Reaction)`
- `(MechanisticClaim, Catalyst, Reaction)`

### 研究价值

这类任务不是直接推荐实验材料，但它能提供**可解释的新方向**。

即不仅告诉你“这个材料可能有效”，还告诉你“可能为什么有效”。

### 现有图谱还需要补的边

建议新增：

- `EvidenceItem --SUPPORTED_BY--> Metric`
你现在只连到了 `PerformanceDataset`，粒度还不够。
真正有用的是：
    - 哪条具体性能指标支持了这个 claim
- `MechanisticClaim --EXPLAINS_PROPERTY--> OntologyTerm(property_name)`
现在 claim 和 performance 之间联系太弱。
需要明确这个机理主要解释什么：
    - activity
    - selectivity
    - stability
    - oxygen demand
    - carbon capture efficiency
    - overpotential
    - FE
    - TOF
- `MechanisticClaim --SIMILAR_TO--> MechanisticClaim`
- `MechanisticClaim --CONFLICTS_WITH--> MechanisticClaim`

这两条边很关键。

因为跨文献时，很多 claim 不是简单重复，而是：

- 相近
- 相反
- 在不同条件下成立

如果没有这两类边，机理层很难用于可信推理。

- `CharacterizationRecord --SUPPORTS_CLAIM--> MechanisticClaim`
- `Metric --SUPPORTS_CLAIM--> MechanisticClaim`

虽然可以通过 `EvidenceItem` 间接连，但建议再建这两个**shortcut edge**，这样图神经网络或路径检索会更有效。

---

## 任务 6：表征方案推荐任务

### 目标边

- `CharacterizationRecord --APPLIES_TO_CATALYST--> Catalyst`
- 或更抽象地预测`Catalyst --> OntologyTerm(method_family)`

### 对应科学问题

“对这个催化剂/反应体系，下一步最值得做什么表征？”

这不是直接“新催化方向”，但非常适合做**实验设计辅助**。

### 现有图谱还需要补的边

建议新增：

- `MechanisticClaim --BEST_PROBED_BY--> OntologyTerm(method_family)`
表示某类机理主张最适合被什么方法验证。
- `CharacterizationRecord --ASSOCIATED_WITH_METRIC--> Metric`
- `CharacterizationRecord --SUPPORTS_CLAIM--> MechanisticClaim`

这样模型能学到：

“如果你关心某种 claim 或某种 property，应该优先做哪类表征”。

---

# 二、建议重点增加的边：按重要性排序

如果只选一批最关键的“新增边”，我建议优先加下面这 12 类。

## 第一优先级：跨文献迁移和比较

这组边最基础。

- `Catalyst --SIMILAR_TO--> Catalyst`
- `Reaction --SIMILAR_TO--> Reaction`
- `Procedure --SIMILAR_TO--> Procedure`
- `OperatingPoint --COMPARABLE_TO--> OperatingPoint`

没有这四类边，跨 paper 的泛化会很弱。

---

## 第二优先级：状态桥接

这组边决定“流程–状态–性能”能不能打通。

- `Procedure --YIELDS_SAMPLE_STATE--> OntologyTerm(sample_state)`
- `Metric --UNDER_SAMPLE_STATE--> OntologyTerm(sample_state)`
- `Reaction --REQUIRES_SAMPLE_STATE--> OntologyTerm(sample_state)`

这三类边会极大提升四元组和五元组预测能力。

---

## 第三优先级：结构–性能桥接

这组边决定能不能学到“为什么好”。

- `Procedure --ASSOCIATED_WITH_METRIC--> Metric`
- `CharacterizationRecord --ASSOCIATED_WITH_METRIC--> Metric`
- `EvidenceItem --SUPPORTED_BY--> Metric`

---

## 第四优先级：机理解释桥接

这组边决定能不能输出“可解释研究方向”。

- `MechanisticClaim --EXPLAINS_PROPERTY--> OntologyTerm(property_name)`
- `CharacterizationRecord --SUPPORTS_CLAIM--> MechanisticClaim`
- `Metric --SUPPORTS_CLAIM--> MechanisticClaim`

---

## 第五优先级：排序与冲突

这组边很适合做 recommendation 和 hard negative mining。

- `Metric --BETTER_THAN--> Metric`
- `Catalyst --OUTPERFORMS--> Catalyst`
- `MechanisticClaim --CONFLICTS_WITH--> MechanisticClaim`

---

# 三、把二元组、三元组、四元组、五元组具体落到你现在的图上

## 1）二元组

最适合直接做 link prediction：

- `(Catalyst, Reaction)`
目标边：`Catalyst --TESTED_IN--> Reaction`
- `(Procedure, Catalyst)`
目标边：`Procedure --APPLIES_TO--> Catalyst`
- `(Procedure, Reaction)`
目标边：`Procedure --SPECIFIC_TO--> Reaction`
- `(MechanisticClaim, Catalyst)`
目标边：`MechanisticClaim --APPLIES_TO_CATALYST--> Catalyst`
- `(MechanisticClaim, Reaction)`
目标边：`MechanisticClaim --ABOUT_REACTION--> Reaction`

---

## 2）三元组

建议做“局部 motif 补全”：

### 三元组 A

`(Catalyst, Procedure, Reaction)`

对应同时满足：

- `Procedure --APPLIES_TO--> Catalyst`
- `Procedure --SPECIFIC_TO--> Reaction`

### 三元组 B

`(Catalyst, Reaction, property_name)`

对应存在某个 `Metric`，满足：

- `Metric --FOR_CATALYST--> Catalyst`
- `Metric --UNDER_REACTION--> Reaction`
- `Metric --TESTS_PROPERTY--> property_name`

### 三元组 C

`(MechanisticClaim, Catalyst, Reaction)`

对应：

- `MechanisticClaim --APPLIES_TO_CATALYST--> Catalyst`
- `MechanisticClaim --ABOUT_REACTION--> Reaction`

---

## 3）四元组

推荐做：

### 四元组 A

`(Catalyst, Reaction, OperatingPoint, property_name)`

这是最标准的“条件化性能预测”。

### 四元组 B

`(Procedure, Catalyst, Reaction, sample_state)`

对应：

- `Procedure --APPLIES_TO--> Catalyst`
- `Procedure --SPECIFIC_TO--> Reaction`
- `Procedure --YIELDS_SAMPLE_STATE--> sample_state`

---

## 4）五元组

最推荐的五元组是：

### 五元组 A

`(Catalyst, Procedure, Reaction, OperatingPoint, property_name)`

这几乎就是“下一轮实验建议”的最自然表达。

### 五元组 B

`(Catalyst, CharacterizationRecord, MechanisticClaim, Reaction, property_name)`

这是“带解释的研究方向”：

- 这个催化剂
- 这个反应
- 哪种机理最可能成立
- 需要哪类表征去验证
- 对哪个性能属性最关键

这个五元组更偏向“机制驱动设计”。

---

# 四、最终建议：先做哪几类任务最划算

如果你现在要开始真正建可预测的图，我建议按这个顺序推进：

第一阶段，先做 3 个主任务：

1. `Catalyst --TESTED_IN--> Reaction`
2. `Procedure --APPLIES_TO--> Catalyst`
3. `Procedure --SPECIFIC_TO--> Reaction`

这是最直接的“新材料–新流程–新反应”方向发现。

第二阶段，做 2 个桥接任务：

4. `CharacterizationRecord --ASSOCIATED_WITH_METRIC--> Metric`

5. `MechanisticClaim --EXPLAINS_PROPERTY--> property_name`

这是把“结构–性能–机理”打通。

第三阶段，再做高阶子图补全：

6. `(Catalyst, Reaction, OperatingPoint, property_name)`

7. `(Catalyst, Procedure, Reaction, OperatingPoint, property_name)`

这时你就能产出真正有实验意义的候选方向。

---

# 五、最简洁的结论

你这张图最适合的预测任务，不是泛泛地“预测任意新边”，而是围绕三条主线：

- **催化剂能不能做这个反应**
- **这个流程能不能迁移到这个催化剂/反应**
- **在这个条件下能不能得到目标性能，并且可能是什么机理**

对应地，现有图谱最应该补的，不是再加很多新节点，而是补足下面几类关键边：

- 相似边：`Catalyst/Reaction/Procedure/OperatingPoint`
- 状态边：`Procedure -> sample_state`，`Metric -> sample_state`
- 结构–性能桥接边：`CharacterizationRecord -> Metric`
- 机理–性能桥接边：`MechanisticClaim -> property_name`，`Metric/CharacterizationRecord -> Claim`
- 排序边：`Metric -> Metric`，`Catalyst -> Catalyst`

这样你的图就会从“事实存储图”变成“可做研究方向推荐的图”。

你要的话，我下一条可以直接把这些任务整理成一份**论文里可用的“预测任务定义 + 新增边设计”正式写法**。

我们可以预测二元组、三元组、甚至四元、五元的组合，都有其实际的意义。
二元组
Catalyst → Reaction：某催化剂是否值得用于某反应
Catalyst → Property/Metric：某体系是否可能有高活性/高选择性/高稳定性
Procedure → Catalyst：某制备/活化流程是否适用于某催化剂；哪类 procedure 会迁移到哪类 catalyst

实例：
某类 phosphide catalyst 未来可能进入 OER
某类 reconstructing catalyst 未来可能被更多论文关联到 stability
某种 activation procedure 未来可能常用于某类 catalyst

三元组：“哪类催化剂，在什么反应里，可能围绕什么性能目标或机理主题成为下一步热点。”
Catalyst – Reaction – Property
Catalyst – Reaction – ClaimType
Catalyst – Reaction – Procedure
Catalyst – Reaction – MethodFamily

实例
NiFe phosphide – OER – low tafel slope
Co-based oxide – CO2RR – high C2 selectivity
reconstructing catalyst – OER – operando XAS evidence
single-atom catalyst – HER – activation pretreatment

四元组/更多 “某个方向大概应该怎么做，在什么条件下做”
Catalyst – Reaction – Property – ConditionPattern
Catalyst – Reaction – Procedure – Property
Catalyst – Reaction – ClaimType – EvidenceType
Catalyst – Reaction – SampleState – MethodFamily
Catalyst – Reaction – PropertyGoal – ConditionPattern – Procedure整体研究假设
Catalyst – Reaction – ClaimType – EvidenceType – MethodFamily未来值得验证的机理
Catalyst – Reaction – SampleState – ClaimType – Property催化剂的结构、状态演化

实例：
NiFe phosphide – OER – low overpotential – alkaline aqueous
CoP-derived catalyst – OER – activation phosphidation – high stability
reconstructing phosphide – OER – active_site_claim – operando XAS
spent catalyst state – OER – XPS/XAS – oxidation-state shift
1.构建一些正样本，用多少年以前的预测以后的，确实成为后来的研究方向了；
2.构建一些负样本，用多少年以前的预测，但是不会形成新方向，也确实没有被研究过，然后专家分析：确实不太行。

**负样本的三类来源**（这是你说的专家验证点）

1. **随机负样本**：完全随机组合本体层节点，从未共现过 → 简单但太容易，模型会过拟合到"组合是否物理合理"
2. **Hard 负样本**：观测窗口内有少量共现，但预测窗口没有增长 → 更难，更有价值
3. **专家标注负样本**：看起来合理但本质有问题的组合（如某类材料的固有缺陷使其永远不适合某反应），专家来判断"确实不行" → 这是最宝贵的，用于校验模型是否学到真正的化学知识

具体实例化：

**2 元组**

- `(catalyst_catalog.labels_material_platform, reaction_catalog.reaction_family)`
- `(catalyst_catalog.labels_active_site_form, reaction_catalog.reaction_family)`
- `(procedure_catalog.procedure_type / steps.step_type, catalyst_catalog.labels_material_platform)`
- `(characterization_records.method_family, mechanistic_claims.claim_type)`
- `(performance.metric.property_name, reaction_catalog.reaction_family)`
意义：发现“哪类材料平台/活性位/工艺/证据方式会进入哪类反应或性能目标”。

**3 元组**

- `(labels_material_platform, reaction_family, property_name)`
- `(labels_active_site_form, reaction_family, property_name)`
- `(labels_material_platform, reaction_family, claim_type)`
- `(labels_material_platform, reaction_family, method_family)`
- `(procedure.steps.step_type, labels_material_platform, reaction_family)`
**哪类催化剂在什么反应里，会围绕什么性能目标/机理主题成为新方向。**

**4 元组**

- `(labels_material_platform, labels_active_site_form, reaction_family, property_name)`
- `(labels_material_platform, reaction_family, property_name, condition_key)`
- `(labels_material_platform, reaction_family, claim_type, evidence_type)`
- `(labels_material_platform, procedure.steps.step_type, reaction_family, property_name)`
- `(sample_state, method_family, claim_type, reaction_family)`
**在什么状态/条件/证据语境下某个研究方向值得做**。

**5 元组**

- `(labels_material_platform, labels_active_site_form, reaction_family, property_name, condition_key)`
- `(labels_material_platform, reaction_family, claim_type, evidence_type, method_family)`
- `(labels_material_platform, procedure.steps.step_type, reaction_family, property_name, target_species)`
- `(labels_material_platform, catalyst_state_during_test, reaction_family, property_name, condition_key)`
- `(sample_state, method_family, claim_type, evidence_type, reaction_family)`
**某类材料平台 + 某活性位形式，在某反应和条件下，追求某指标，并优先用某类表征去验证某类机理。**

你的构想已经非常接近正确答案，但有几个细节需要仔细设计：

**时间切分策略（对齐 Marwitz）**

- 观测窗口：`[1990, T_cut]`，用这段历史构建图和特征
- 预测窗口：`[T_cut, T_cut+5]`，判断 tuple 是否"爆发"
- 可以用多个 T_cut 做滑窗（如 2010、2012、2014、2016），增加样本量

**"爆发"的量化定义**（最容易踩坑的地方）
不能只看绝对数量，因为有的领域本来发文就多。建议用：

- 相对增长率：`count(T+5) / count(T) > θ`，且 `count(T)` 有最低门槛（至少出现过 k 次，避免从 0→1 也算爆发）
- 或 Δ-surprise：实际增长 vs. 基于历史趋势的预期增长的偏差
