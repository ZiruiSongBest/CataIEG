### 1）新增“规范化实体层”   催化剂按元素-作用再细分

这是最重要的结构改造。

### 建议新增节点

### a. `ReactionTemplate`

不是 paper 里的某个 `R1`，而是跨文献归一后的反应模板。

例如：

- 甲烷干重整
- CO₂ hydrogenation to methanol
- NH₃ decomposition
- OER / ORR / HER 的更细模板

建议边：

- `Reaction --INSTANCE_OF_TEMPLATE--> ReactionTemplate`
- `ReactionTemplate --IN_FAMILY--> OntologyTerm(reaction_family)`
- `ReactionTemplate --IN_CLASS--> OntologyTerm(reaction_class)`

### b. `CatalystFamily`

不是 `C1`，而是“可跨文献合并”的催化剂家族。

例如：

- Ni/CeO2
- Cu-ZnO-Al2O3 family
- Fe-N-C SAC
- CoOx spinel family

建议边：

- `Catalyst --INSTANCE_OF_FAMILY--> CatalystFamily`
- `CatalystFamily --HAS_MATERIAL_PLATFORM--> OntologyTerm(material_platform)`
- `CatalystFamily --HAS_ACTIVE_SITE_FORM--> OntologyTerm(active_site_form)`
- `CatalystFamily --HAS_MORPHOLOGY_FORM--> OntologyTerm(morphology_device_form)`

### c. `ProcedureTemplate`

把具体 `P1` 归一成跨文献模板：

- co-precipitation
- impregnation + drying + calcination
- solvothermal + annealing
- ion exchange + reduction

建议边：

- `Procedure --INSTANCE_OF_TEMPLATE--> ProcedureTemplate`
- `ProcedureTemplate --IN_PROCEDURE_TYPE--> OntologyTerm(procedure_type)`

### d. `ObservationType`

这是你现在明显缺的一层。

因为 `CharacterizationRecord.results` 现在还是个 blob/list，但对机理推断真正关键的是**观察到什么现象**。

例如：

- high dispersion
- oxygen vacancy enriched
- strong metal-support interaction
- isolated M–N₄ site
- lattice oxygen participation
- phase segregation
- particle sintering suppressed

建议边：

- `CharacterizationRecord --HAS_OBSERVATION--> Observation`
- `Observation --INSTANCE_OF--> ObservationType`
- `Observation --ABOUT_CATALYST--> Catalyst / CatalystFamily`
- `Observation --UNDER_SAMPLE_STATE--> OntologyTerm(sample_state)`
- `Observation --DERIVED_FROM_METHOD--> OntologyTerm(method_family)`

这是把“表征记录容器”变成“可推理现象”的关键。

### e. `ConditionContext / ConditionBin`

既然不做数值预测，那就把条件离散化成上下文桶。

例如：

- `temperature_regime = low / medium / high`
- `pressure_regime`
- `electrolyte_type`
- `pH_regime`
- `potential_window`
- `feed_ratio_regime`
- `GHSV_regime`

建议边：

- `OperatingPoint --HAS_CONTEXT--> ConditionContext`
- `ProcedureStep --HAS_PARAMETER_BIN--> ConditionBin`

这样你做的是**条件上下文趋势预测**，不是数值回归。

### f. `OutcomeLabel`

从 `Metric` 派生，但不是数值。

例如：

- active_reported
- selective_reported
- stable_reported
- improved_vs_baseline
- deactivation_resistant
- coke_resistant

建议边：

- `Metric / PerformanceDataset --HAS_OUTCOME_LABEL--> OutcomeLabel`

这一步非常关键，因为“研究方向预测”往往需要知道什么被认为是“ promising ”，否则图里只有“测过”，没有“值得继续做”。

---

### 2）把字符串字段变成真正的节点

你现在有几块信息还是字符串数组，这会严重限制可预测性。

### 必须节点化的字段

### a. `Reaction.reactants` / `target_products`

建议变成：

- `Species` 或 `Molecule` 节点
- 边：
    - `ReactionTemplate --HAS_REACTANT--> Species`
    - `ReactionTemplate --HAS_PRODUCT--> Species`

否则你无法做：

- 哪类底物更容易导向哪类催化体系
- 哪类转化模板之间可以迁移催化剂设计

### b. `ProcedureStep.inputs` / `output_intermediate`

建议变成：

- `MaterialEntity` / `IntermediateState` 节点
- 边：
    - `ProcedureStep --USES_INPUT--> MaterialEntity`
    - `ProcedureStep --YIELDS_INTERMEDIATE--> IntermediateState`

### c. 催化剂组成拆解

目前 `Catalyst` 还太整体化。建议拆成：

- `Component`（元素/氧化物/配体/载体）
- `Role`（active metal / support / promoter / dopant / precursor）

建议边：

- `CatalystFamily --HAS_ACTIVE_COMPONENT--> Component`
- `CatalystFamily --HAS_SUPPORT--> Component`
- `CatalystFamily --HAS_PROMOTER--> Component`
- `CatalystFamily --HAS_DOPANT--> Component`
- `CatalystFamily --DERIVED_FROM_PRECURSOR--> Component`

没有这一层，就很难从“平台级”走到“可操作的具体方向”。

---

### 3）增加“事实节点 / 事件节点”，不要只靠链式二元边

你现在的链式结构：

- `Reaction -> Dataset -> OperatingPoint -> Metric -> Catalyst`
- `Claim -> Evidence -> Char/Perf/Procedure`

很适合存 provenance，

但不太适合直接做三元、四元、五元预测。

我建议新增三类**事实节点**：

### a. `CatalyticTestFact`

表示一个完整测试事实：

- 连接：`ReactionTemplate`、`CatalystFamily`、`ConditionContext`、`OutcomeLabel`
- 作用：用于预测缺失的催化剂、条件、结果标签

### b. `SynthesisFact`

表示一个完整制备事实：

- 连接：`CatalystFamily`、`ProcedureTemplate`、`StepSequencePattern`、`ConditionBin`、`ObservationType/ActiveSiteForm`
- 作用：用于预测什么路线会导向什么结构特征

### c. `MechanismFact`

表示一个完整机理事实：

- 连接：`ReactionTemplate`、`CatalystFamily`、`ObservationType`、`ClaimTheme`、`MethodFamily/EvidenceType`
- 作用：用于预测新的三元/四元/五元研究假说

这类 reified fact / statement node 的设计，本质上是在 property graph 里模拟 n-ary fact；对于你这种目标，比只存二元边更合适。

---

### 4）把“步骤序列”从线性链升级为“步骤模式”

你现在有：

- `Procedure --HAS_STEP--> Step`
- `Step --NEXT_STEP--> Step`

这很好，但如果要预测新的制备路线，还不够。

建议新增：

### `StepSignature`

把 step 规范化成“操作 + 条件桶 + 物料角色”的模式，例如：

- impregnation @ ambient drying precursor-loaded support
- calcination @ high-T in air
- reduction @ H₂ medium-T
- acid leaching @ low-pH

建议边：

- `ProcedureStep --INSTANCE_OF_SIGNATURE--> StepSignature`
- `StepSignature --NEXT_SIGNATURE--> StepSignature`

进一步可以把一个完整 sequence 再压成：

- `StepSequencePattern`

这样才能做：

- `(material_platform, active_site_form) -> step sequence`
- `(CatalystFamily, ?) -> next_step_signature`

---

### 5）强化机理层：Claim 不该只连到“记录容器”，还要连到“现象对象”

目前：

- `MechanisticClaim -> EvidenceItem -> CharacterizationRecord/PerformanceDataset/Procedure`

建议再补：

- `MechanisticClaim --SUPPORTED_BY_OBSERVATION--> Observation`
- `MechanisticClaim --SUPPORTED_BY_OUTCOME--> OutcomeLabel`
- `MechanisticClaim --CONCERNS_ACTIVE_SITE--> OntologyTerm(active_site_form)`
- `MechanisticClaim --CONCERNS_INTERMEDIATE--> Species / IntermediateType`
- `MechanisticClaim --CONCERNS_STEP--> ReactionElementaryStepType`（如果后面能抽）

以及把 `EvidenceItem` 的关系分成：

- `SUPPORTS`
- `WEAKLY_SUPPORTS`
- `REFUTES`
- `IS_CONSISTENT_WITH`

否则以后做 claim/evidence 预测时，边的语义太粗。

### 6）本体层之间最好补层级边，但“统计共现”不要混进纯本体

你说本体节点之间目前互不链接。

我建议至少补最基础的：

- `IS_A`
- `PART_OF`
- `SUBTYPE_OF`
- `RELATED_TO`

例如：

- `single_atom_site IS_A isolated_site`
- `perovskite IS_A mixed_oxide_platform`
- `calcination SUBTYPE_OF thermal_treatment`

但要注意：

**“本体定义边”** 和 **“文献统计边/趋势边”** 最好分开。

也就是说：

- 本体里放 `IS_A`、`PART_OF`
- 趋势图里放 `LIKELY_USES`、`CO_OCCURS_WITH`、`EMERGING_WITH`

不要把统计关系写成本体事实。

---

## 四、我建议你优先新增的边

如果只选最关键的一批，我会选下面这些。

### 规范化实体层边

- `Reaction --INSTANCE_OF_TEMPLATE--> ReactionTemplate`
- `Catalyst --INSTANCE_OF_FAMILY--> CatalystFamily`
- `Procedure --INSTANCE_OF_TEMPLATE--> ProcedureTemplate`
- `ProcedureStep --INSTANCE_OF_SIGNATURE--> StepSignature`
- `CharacterizationRecord --HAS_OBSERVATION--> Observation`
- `Observation --INSTANCE_OF--> ObservationType`
- `OperatingPoint --HAS_CONTEXT--> ConditionContext`
- `Metric/PerformanceDataset --HAS_OUTCOME_LABEL--> OutcomeLabel`

### 组成与反应对象边

- `CatalystFamily --HAS_ACTIVE_COMPONENT--> Component`
- `CatalystFamily --HAS_SUPPORT--> Component`
- `CatalystFamily --HAS_PROMOTER--> Component`
- `CatalystFamily --HAS_DOPANT--> Component`
- `ReactionTemplate --HAS_REACTANT--> Species`
- `ReactionTemplate --HAS_PRODUCT--> Species`

### 机理增强边

- `MechanisticClaim --SUPPORTED_BY_OBSERVATION--> Observation`
- `MechanisticClaim --SUPPORTED_BY_OUTCOME--> OutcomeLabel`
- `MechanisticClaim --CONCERNS_ACTIVE_SITE--> OntologyTerm(active_site_form)`
- `MechanisticClaim --TYPICALLY_VERIFIED_BY--> OntologyTerm(method_family)`
这个可作为可学习边，而不一定全是抽取边

### 模板/趋势预测目标边

- `ReactionTemplate --CANDIDATE_FOR--> CatalystFamily`
- `CatalystFamily --LIKELY_PREPARED_BY--> ProcedureTemplate`
- `ReactionFamilyOnto --LIKELY_USES--> MaterialPlatformOnto`
- `ReactionFamilyOnto --LIKELY_ASSOCIATED_WITH--> ActiveSiteFormOnto`
- `ClaimTypeOnto --TYPICALLY_SUPPORTED_BY--> MethodFamilyOnto`

---

## 五、一个更适合你的最小可行任务集

如果你现在就要开始做，我建议先做这 6 个，够强，也最稳：

### 第一批（马上能用）

1. `reaction_family -> material_platform`
2. `reaction_family -> active_site_form`
3. `material_platform -> procedure_type`
4. `claim_type -> method_family`
5. `ReactionTemplate -> CatalystFamily`
6. `(ReactionTemplate, CatalystFamily) -> ClaimTheme`

这 6 个里：

- 前 4 个偏本体层，适合趋势预测
- 后 2 个偏规范化实体层，适合方向发现