
## 实例层 + 本体层 + 文献层

整体分成 8 类节点：

- 文献节点 `Paper`
- 反应节点 `Reaction`
- 催化剂节点 `Catalyst`
- 制备流程节点 `Procedure / Step`
- 表征节点 `CharacterizationRecord / Result`
- 性能节点 `PerformanceDataset / OperatingPoint / Metric`
- 机理主张节点 `MechanisticClaim / EvidenceItem`
- 本体节点

## 一、分配全局唯一 ID

当前 `R1/C1/P1/CR1/PR1/MC1` 只在单篇 paper 内唯一。建图时必须扩成全局 ID，否则跨文献时会冲突

- `paper:10.1016_jcat_2019_02_014`
- `reaction:10.1016_jcat_2019_02_014:R1`

```
paper_uid      = paper:<doi_norm>
reaction_uid   = reaction:<doi_norm>:R1
catalyst_uid   = catalyst:<doi_norm>:C1
procedure_uid  = procedure:<doi_norm>:P1
step_uid       = step:<doi_norm>:P1:S2
char_uid       = char:<doi_norm>:CR1
dataset_uid    = perf:<doi_norm>:PR1
op_uid         = op:<doi_norm>:PR1:OP1
metric_uid     = metric:<doi_norm>:PR1:OP1:C1:M1
claim_uid      = claim:<doi_norm>:MC1
evidence_uid   = evidence:<doi_norm>:MC1:E1
ontology_uid   = onto:<type>:<name>
```

## 二、节点设计：每类节点的 key

### 1）Paper

```
{
  "paper_uid":"paper:10.1016_jcat_2019_02_014",
  "doi":"10.1016/j.jcat.2019.02.014",
  "title":"...",
  "journal":"...",
  "year":2019
}
```

一篇文章一个节点，Paper节点 负责来源容器、局部 ID 作用域、去重单位和证据追溯起点。

### 2）Reaction

```
{
  "reaction_uid":"reaction:<doi_norm>:R1",
  "local_id":"R1",
  "reaction_name_reported":"...",
  "transformation":"...",
  "reaction_domain":"...",
  "reaction_class":"...",
  "reaction_family": ["..."],
  "reactants": ["..."],
  "target_products": ["..."],
}
```

对应 `reaction_catalog`，每个 `reaction_id` 一个节点

### 3）Catalyst

```
{
  "catalyst_uid":"catalyst:<doi_norm>:C1",
  "local_id":"C1",
  "name_reported":"...",
  "series_name":"...",
  "variant_rule":"...",
  "variant_value":"...",
  "substrate_or_support":"...",
  "form_factor": ["..."],
  "labels_material_platform": ["..."],
  "labels_active_site_form": ["..."],
  "labels_morphology_device_form": ["..."],
  "tested_reaction_ids": ["R1","R2"]
}
```

对应 `catalyst_catalog`，一个catalyst_id一个节点。tested_reaction_ids表示C1和R1、R2连接。

### 4）Procedure

```
{
  "procedure_uid":"procedure:<doi_norm>:P1",
  "local_id":"P1",
  "procedure_type":"...",
  "name_reported":"...",
  "reaction_ids": ["R1"],
  "catalyst_ids": ["C1","C2"]
}
```

对应 `procedure_catalog` 的每个 `P1/P2/...`。节点中的"reaction_ids"和"catalyst_ids"表示P1分别和R1、C1、C2相连。

### 5）ProcedureStep

```
{
  "step_uid":"step:<doi_norm>:P1:S2",
  "procedure_uid":"procedure:<doi_norm>:P1",
  "step_no":2,
  "step_type":"...",
  "method_details":"...",
  "inputs": ["..."],
  "parameters": {
    "temperature": "...",
    "time": "...",
    "atmosphere": "...",
    "pressure": "...",
    "concentration": "...",
    "pH": "...",
    "ramp_rate": "...",
    "stirring": "...",
    "other": "..."
  },
  "output_intermediate":"..."
}
```

Procedure 表示完整 workflow，Step 表示其中的步骤序列。一个Procedure 下每个Step是一个节点。Procedure 与其下每个Step节点相连，Step节点之间按"step_no"顺序连接。

### 6）CharacterizationRecord

```
{
  "char_uid":"char:<doi_norm>:CR1",
  "local_id":"CR1",
  "catalyst_id":"C1",
  "applies_to_catalyst_ids": ["C2","C3"]
  "sample_state":"...",
  "reaction_id":"R1",
  "method_family":"...",
  "method_name_reported":"..."
  "results": [...]
}
```

每个characterization_records下的record_id是一个CharacterizationRecord节点。CR1与C1、C2、C3、R1相连

### 7）PerformanceDataset

```
{
  "dataset_uid":"perf:<doi_norm>:PR1",
  "local_id":"PR1",
  "reaction_id":"R1",
  "dataset_type":"...",
  "common_conditions": {...}
}
```

”performance_records”下的一个"dataset_id”是一个节点。与R1相连

### 8）OperatingPoint

```
{
  "op_uid":"op:<doi_norm>:PR1:OP1",
  "point_id":"OP1",
  "point_conditions": {...}
}
```

”performance_records”_"dataset_id”_"operating_points"下的每一个"point_id"是一个节点。PR1与其下的每一个OperatingPoint节点相连，OP1与OP2之间不相连

### 9）Metric

```
{
  "metric_uid":"metric:<doi_norm>:PR1:OP1:C1:M1",
  "reaction_id":"R1",
  "catalyst_id":"C1",
  "catalyst_state_during_test":"...",
  "state_notes":"...",
  "property_name":"...",
  "target_species":"...",
  "basis":"...",
  "value":"...",
  "unit":"...",
  "notes":"..."
}
```

一个"point_id"下的每一个"metrics_by_catalyst"是一个节点。与相应的OperatingPoint节点相连，M1与M2不相连。与  "reaction_id":"R1", "catalyst_id":"C1"相连。

### 10）MechanisticClaim

```
{
  "claim_uid":"claim:<doi_norm>:MC1",
  "local_id":"MC1",
  "reaction_id":"R1",
  "catalyst_id":"C1",
  "applies_to_catalyst_ids": ["C2","C3"],
  "claim_type":"...",
  "design_mechanism_tags": ["..."],
  "claim_summary":"..."
}
```

一个"claim_id"是一个节点MC1，与  "reaction_id":"R1", "catalyst_id":"C1", "applies_to_catalyst_ids":["C2","C3"]    R1、C1、C2、C3相连。

### 11）EvidenceItem

```
{
  "evidence_uid":"evidence:<doi_norm>:MC1:E1",
  "evidence_type":"...",
  "evidence_summary":"..."
  "linked_characterization_record_ids": ["CR1"],
	"linked_performance_dataset_ids": ["PR1"],
	"linked_procedure_ids": ["P1"]
}
```

"evidence_chain"中的每一项是一个节点，按 
        "linked_characterization_record_ids": ["CR1"],
	"linked_performance_dataset_ids": ["PR1"],
	"linked_procedure_ids": ["P1"]
连接到该Paper下的CR1、PR1、P1。

所以结构是MechanisticClaim （连接到Reaction/Catalyst） -> EvidenceItem -> CharacterizationRecord / PerformanceDataset / Procedure

### 13）OntologyTerm（统一承载所有本体节点，概念层）

```
{
  "ontology_uid":"onto:<ontology_type>:<canonical_name>",
  "ontology_type":"reaction_family",  #对应本体节点的key
  "canonical_name":"OER",  #对应本体节点的value
}
```

这一层的作用是标准化、桥接、分层检索和层级泛化。

canonical_name来自prompt的枚举库，每一个canonical_name是一个本体节点

`ontology_type` 包括：

Reaction节点中的

- reaction_domain
- reaction_class
- reaction_family

Catalyst 节点

- material_platform
- active_site_form
- morphology_device_form
- form_factor

Procedure 节点

- procedure_type

ProcedureStep 节点

- step_type

CharacterizationRecord节点

- sample_state
- method_family

PerformanceDataset 节点

- dataset_type

Metric 节点

- property_name
- target_species
- basis

MechanisticClaim 节点

- claim_type
- design_mechanism_tag

EvidenceItem 节点

- evidence_type

**连接**：每个本体节点与所属概念的实例节点相连。比如某个reaction节点里包含"reaction_family":"OER"，那么就与该本体节点  "ontology_uid":"onto:reaction_family:OER"相连。

本体节点之间虽然有一些从属关系，但简单起见互不链接。

## 三、有向边设计

### 1. 根据现有json数据能直接构建的边

### A. 文献-实例边

这些边是 Paper 与局部子图的实例之间的关系（一篇文章中包含哪些信息，与实例层的主节点相连，与ProcedureStep、OperatingPoint这些不相连）。

- `Paper --HAS_REACTION--> Reaction`
- `Paper --HAS_CATALYST--> Catalyst`
- `Paper --HAS_PROCEDURE--> Procedure`
- `Paper --HAS_CHARACTERIZATION--> CharacterizationRecord`
- `Paper --HAS_PERFORMANCE_DATASET--> PerformanceDataset`
- `Paper --HAS_MECHANISTIC_CLAIM--> MechanisticClaim`

### B. 实例-实例边

反应—催化剂边

`Catalyst --TESTED_IN--> Reaction`

流程相关边

- `Procedure --APPLIES_TO--> Catalyst`
- `Procedure --SPECIFIC_TO--> Reaction`
- `Procedure --HAS_STEP--> ProcedureStep`
- `ProcedureStep --NEXT_STEP--> ProcedureStep`

表征相关边

- `CharacterizationRecord --APPLIES_TO_CATALYST--> Catalyst`
- `CharacterizationRecord --LINKED_TO_REACTION--> Reaction`

性能相关边

- `Reaction --HAS_PERFORMANCE_DATASET--> PerformanceDataset`
- `PerformanceDataset --HAS_OPERATING_POINT--> OperatingPoint`
- `OperatingPoint --HAS_METRIC--> Metric`
- `Metric --FOR_CATALYST--> Catalyst`
- `Metric --UNDER_REACTION--> Reaction`

 机理与证据边

- `MechanisticClaim --ABOUT_REACTION--> Reaction`
- `MechanisticClaim --APPLIES_TO_CATALYST--> Catalyst`
- `MechanisticClaim --HAS_EVIDENCE--> EvidenceItem`
- `EvidenceItem --SUPPORTED_BY--> CharacterizationRecord`
- `EvidenceItem --SUPPORTED_BY--> PerformanceDataset`
- `EvidenceItem --SUPPORTED_BY--> Procedure`

### C. 本体映射边

- `Reaction --IN_DOMAIN--> OntologyTerm(reaction_domain)`
- `Reaction --IN_CLASS--> OntologyTerm(reaction_class)`
- `Reaction --IN_FAMILY--> OntologyTerm(reaction_family)`
- `Catalyst --HAS_MATERIAL_PLATFORM--> OntologyTerm(material_platform)`
- `Catalyst --HAS_ACTIVE_SITE_FORM--> OntologyTerm(active_site_form)`
- `Catalyst --HAS_MORPHOLOGY_FORM--> OntologyTerm(morphology_device_form)`
- `Catalyst --HAS_FORM_FACTOR--> OntologyTerm(form_factor)`
- `Procedure --IN_PROCEDURE_TYPE--> OntologyTerm(procedure_type)`
- `ProcedureStep --IN_STEP_TYPE--> OntologyTerm(step_type)`
- `CharacterizationRecord --UNDER_SAMPLE_STATE--> OntologyTerm(sample_state)`
- `CharacterizationRecord --USES_METHOD--> OntologyTerm(method_family)`
- `PerformanceDataset --TESTS_PROPERTY_TYPE--> OntologyTerm(dataset_type)`
- `Metric --TESTS_PROPERTY--> OntologyTerm(property_name)`
- `Metric --TESTS_TARGET_SPECIES--> OntologyTerm(target_species)`
- `Metric --TESTS_UNDER_BASIS--> OntologyTerm(basis)`
- `MechanisticClaim --HAS_CLAIM_TYPE--> OntologyTerm(claim_type)`
- `MechanisticClaim --HAS_TAG--> OntologyTerm(design_mechanism_tag)`
- `EvidenceItem --HAS_EVIDENCE_TYPE--> OntologyTerm(evidence_type)`

### 2. 为实现预测任务要构造的边

### 

[新添加的边](new-edge.md)

[催化图谱补充](supplyment.md)