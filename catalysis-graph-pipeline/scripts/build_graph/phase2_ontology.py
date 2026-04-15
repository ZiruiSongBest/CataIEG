"""Phase 2: 从实例节点提取本体层节点和映射边"""


# 本体映射配置：(node_type, field_name, ontology_type, edge_type, is_list)
ONTOLOGY_MAPPINGS = [
    ("Reaction", "reaction_domain", "reaction_domain", "IN_DOMAIN", False),
    ("Reaction", "reaction_class", "reaction_class", "IN_CLASS", False),
    ("Reaction", "reaction_family", "reaction_family", "IN_FAMILY", True),
    ("Catalyst", "labels_material_platform", "material_platform", "HAS_MATERIAL_PLATFORM", True),
    ("Catalyst", "labels_active_site_form", "active_site_form", "HAS_ACTIVE_SITE_FORM", True),
    ("Catalyst", "labels_morphology_device_form", "morphology_device_form", "HAS_MORPHOLOGY_FORM", True),
    ("Catalyst", "form_factor", "form_factor", "HAS_FORM_FACTOR", True),
    ("Procedure", "procedure_type", "procedure_type", "IN_PROCEDURE_TYPE", False),
    ("ProcedureStep", "step_type", "step_type", "IN_STEP_TYPE", False),
    ("CharacterizationRecord", "sample_state", "sample_state", "UNDER_SAMPLE_STATE", False),
    ("CharacterizationRecord", "method_family", "method_family", "USES_METHOD", False),
    ("PerformanceDataset", "dataset_type", "dataset_type", "TESTS_PROPERTY_TYPE", False),
    ("Metric", "property_name", "property_name", "TESTS_PROPERTY", False),
    ("Metric", "target_species", "target_species", "TESTS_TARGET_SPECIES", False),
    ("Metric", "basis", "basis", "TESTS_UNDER_BASIS", False),
    ("Metric", "catalyst_state_during_test", "catalyst_state", "UNDER_CATALYST_STATE", False),
    ("MechanisticClaim", "claim_type", "claim_type", "HAS_CLAIM_TYPE", False),
    ("MechanisticClaim", "design_mechanism_tags", "design_mechanism_tag", "HAS_TAG", True),
    ("EvidenceItem", "evidence_type", "evidence_type", "HAS_EVIDENCE_TYPE", False),
]


def _normalize_onto_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def build_ontology_layer(instance_nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    onto_nodes = {}  # uid -> node dict
    edges = []

    # 按 node_type 索引实例节点
    nodes_by_type = {}
    for n in instance_nodes:
        nt = n["node_type"]
        nodes_by_type.setdefault(nt, []).append(n)

    for node_type, field_name, onto_type, edge_type, is_list in ONTOLOGY_MAPPINGS:
        for node in nodes_by_type.get(node_type, []):
            raw = node.get(field_name)
            if raw is None:
                continue

            values = raw if is_list and isinstance(raw, list) else [raw]
            for val in values:
                if not val or not isinstance(val, str):
                    continue
                canon = _normalize_onto_name(val)
                if not canon:
                    continue

                onto_uid = f"onto:{onto_type}:{canon}"
                if onto_uid not in onto_nodes:
                    onto_nodes[onto_uid] = {
                        "uid": onto_uid,
                        "node_type": "OntologyTerm",
                        "ontology_type": onto_type,
                        "canonical_name": canon,
                        "display_name": val.strip(),
                    }

                edges.append({
                    "source": node["uid"],
                    "target": onto_uid,
                    "edge_type": edge_type,
                })

    return list(onto_nodes.values()), edges
