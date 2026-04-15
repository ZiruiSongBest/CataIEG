"""Phase 4: 跨文献桥接层 —— 本体共现边 + 规范化实体共研边 + 相似度边"""
from collections import defaultdict
from config import normalize_doi


# ===== 4a: 本体-本体共现边（实例级别） =====
#
# 设计原则（需求 6）：
#   共现不是"出现在同一篇论文"，而是"属于它们的实例在同一篇论文中确实被共同研究"。
#   例如 Paper 有 R1,R2,C1,C2 且 C1→R1, C2→R2，则 C1 和 R2 的本体标签不共现。
#
# 实现方式：
#   以每个 (Catalyst, Reaction) TESTED_IN 对为一个"共研上下文"，
#   收集该对涉及的所有实例（Catalyst, Reaction, 以及通过边连接的 Procedure,
#   ProcedureStep, PerformanceDataset, OperatingPoint, Metric, CharacterizationRecord）
#   的本体标签，在这个上下文内部做两两共现。
#
# 允许的有向共现对和边类型（需求 7）：
_DIRECTED_PAIRS = {
    # (source_type, target_type): edge_type
    ("reaction_family", "material_platform"):  "LIKELY_USES",
    ("reaction_family", "active_site_form"):   "LIKELY_ASSOCIATED_WITH",
    ("active_site_form", "property_name"):     "LIKELY_ASSOCIATED_WITH",
    ("material_platform", "property_name"):    "LIKELY_ASSOCIATED_WITH",
    ("reaction_family", "step_type"):          "LIKELY_ASSOCIATED_WITH",
    ("material_platform", "step_type"):        "LIKELY_ASSOCIATED_WITH",
    ("active_site_form", "step_type"):         "LIKELY_ASSOCIATED_WITH",
    # design_mechanism_tag 相关（预留，当上游有 mechanistic_claims 数据时生效）
    ("reaction_family", "design_mechanism_tag"):  "LIKELY_SUPPORTS",
    ("active_site_form", "design_mechanism_tag"): "LIKELY_SUPPORTS",
    ("material_platform", "design_mechanism_tag"): "LIKELY_SUPPORTS",
    ("property_name", "design_mechanism_tag"):    "LIKELY_SUPPORTS",
}

# 快速查找：任意方向都要能匹配
_PAIR_LOOKUP = {}  # (type_a, type_b) -> (source_type, target_type, edge_type)
for (st, tt), et in _DIRECTED_PAIRS.items():
    _PAIR_LOOKUP[(st, tt)] = (st, tt, et)
    _PAIR_LOOKUP[(tt, st)] = (st, tt, et)  # 反向查到同一定义，但保持有向性


def build_co_studied_edges(
    papers: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> list[dict]:
    """基于实例级别连接关系推导本体-本体共现边。"""

    uid_to_node = {n["uid"]: n for n in all_nodes}

    # ---- 1. 建索引 ----

    # 本体映射：instance_uid → set(onto_uid)
    _ONTO_EDGE_TYPES = {
        "IN_DOMAIN", "IN_CLASS", "IN_FAMILY",
        "HAS_MATERIAL_PLATFORM", "HAS_ACTIVE_SITE_FORM",
        "HAS_MORPHOLOGY_FORM", "HAS_FORM_FACTOR",
        "IN_PROCEDURE_TYPE", "IN_STEP_TYPE",
        "UNDER_SAMPLE_STATE", "USES_METHOD",
        "TESTS_PROPERTY_TYPE", "TESTS_PROPERTY",
        "TESTS_TARGET_SPECIES", "TESTS_UNDER_BASIS",
        "UNDER_CATALYST_STATE",
        "HAS_CLAIM_TYPE", "HAS_TAG", "HAS_EVIDENCE_TYPE",  # 预留
    }
    instance_to_ontos = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] in _ONTO_EDGE_TYPES:
            instance_to_ontos[e["source"]].add(e["target"])

    # onto_uid → ontology_type
    onto_type_map = {}
    for n in all_nodes:
        if n["node_type"] == "OntologyTerm":
            onto_type_map[n["uid"]] = n["ontology_type"]

    # 各类实例级别连接索引
    # Catalyst --TESTED_IN--> Reaction
    tested_in_pairs = []  # [(cat_uid, rxn_uid)]
    for e in all_edges:
        if e["edge_type"] == "TESTED_IN":
            tested_in_pairs.append((e["source"], e["target"]))

    # Procedure --APPLIES_TO--> Catalyst
    proc_to_cats = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "APPLIES_TO":
            proc_to_cats[e["source"]].add(e["target"])

    # Procedure --SPECIFIC_TO--> Reaction
    proc_to_rxns = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "SPECIFIC_TO":
            proc_to_rxns[e["source"]].add(e["target"])

    # Procedure --HAS_STEP--> ProcedureStep
    proc_to_steps = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "HAS_STEP":
            proc_to_steps[e["source"]].add(e["target"])

    # CharacterizationRecord --APPLIES_TO_CATALYST--> Catalyst
    char_to_cats = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "APPLIES_TO_CATALYST":
            char_to_cats[e["source"]].add(e["target"])

    # CharacterizationRecord --LINKED_TO_REACTION--> Reaction
    char_to_rxns = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "LINKED_TO_REACTION":
            char_to_rxns[e["source"]].add(e["target"])

    # Metric --FOR_CATALYST--> Catalyst, Metric --UNDER_REACTION--> Reaction
    metric_to_cat = {}
    metric_to_rxn = {}
    for e in all_edges:
        if e["edge_type"] == "FOR_CATALYST":
            metric_to_cat[e["source"]] = e["target"]
        elif e["edge_type"] == "UNDER_REACTION":
            metric_to_rxn[e["source"]] = e["target"]

    # OperatingPoint --HAS_METRIC--> Metric
    op_to_metrics = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "HAS_METRIC":
            op_to_metrics[e["source"]].add(e["target"])

    # PerformanceDataset --HAS_OPERATING_POINT--> OperatingPoint
    perf_to_ops = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "HAS_OPERATING_POINT":
            perf_to_ops[e["source"]].add(e["target"])

    # Reaction --HAS_PERFORMANCE_DATASET--> PerformanceDataset
    rxn_to_perfs = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "HAS_PERFORMANCE_DATASET":
            rxn_to_perfs[e["source"]].add(e["target"])

    # Paper --HAS_CHARACTERIZATION--> CharacterizationRecord
    # Paper --HAS_PROCEDURE--> Procedure
    # Paper --HAS_MECHANISTIC_CLAIM--> MechanisticClaim
    paper_chars = defaultdict(set)
    paper_procs = defaultdict(set)
    paper_claims = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "HAS_CHARACTERIZATION":
            paper_chars[e["source"]].add(e["target"])
        elif e["edge_type"] == "HAS_PROCEDURE":
            paper_procs[e["source"]].add(e["target"])
        elif e["edge_type"] == "HAS_MECHANISTIC_CLAIM":
            paper_claims[e["source"]].add(e["target"])

    # MechanisticClaim --APPLIES_TO_CATALYST--> Catalyst
    claim_to_cats = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "APPLIES_TO_CATALYST" and e["source"].startswith("claim:"):
            claim_to_cats[e["source"]].add(e["target"])

    # MechanisticClaim --ABOUT_REACTION--> Reaction
    claim_to_rxns = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "ABOUT_REACTION":
            claim_to_rxns[e["source"]].add(e["target"])

    # MechanisticClaim --HAS_EVIDENCE--> EvidenceItem
    claim_to_evidence = defaultdict(set)
    for e in all_edges:
        if e["edge_type"] == "HAS_EVIDENCE":
            claim_to_evidence[e["source"]].add(e["target"])

    # paper 年份
    paper_years = {}
    doi_to_paper = {}
    for n in all_nodes:
        if n["node_type"] == "Paper":
            paper_years[n["uid"]] = n.get("year")
            doi_to_paper[normalize_doi(n["doi"])] = n["uid"]

    # ---- 2. 为每个 (Catalyst, Reaction) 对构建"共研上下文" ----

    def _collect_onto_tags(uid_set: set) -> set:
        """从一组实例 uid 收集所有本体标签"""
        tags = set()
        for uid in uid_set:
            tags.update(instance_to_ontos.get(uid, set()))
        return tags

    # key = (onto_uid_source, onto_uid_target, edge_type)
    co_occur = defaultdict(lambda: {"count": 0, "papers": set(), "years": []})

    for cat_uid, rxn_uid in tested_in_pairs:
        doi_norm = cat_uid.split(":")[1]
        paper_uid = doi_to_paper.get(doi_norm)
        if not paper_uid:
            continue
        year = paper_years.get(paper_uid)

        # 收集这个 (C, R) 对涉及的所有实例节点
        context_uids = {cat_uid, rxn_uid}

        # Procedures: 同时 APPLIES_TO 该 Catalyst 且 SPECIFIC_TO 该 Reaction 的
        # 或者只 APPLIES_TO 该 Catalyst（有些 Procedure 没有 SPECIFIC_TO）
        for proc_uid in paper_procs.get(paper_uid, set()):
            cats = proc_to_cats.get(proc_uid, set())
            rxns = proc_to_rxns.get(proc_uid, set())
            if cat_uid in cats and (not rxns or rxn_uid in rxns):
                context_uids.add(proc_uid)
                context_uids.update(proc_to_steps.get(proc_uid, set()))

        # CharacterizationRecords: APPLIES_TO_CATALYST 包含该 Catalyst 的
        for char_uid in paper_chars.get(paper_uid, set()):
            cats = char_to_cats.get(char_uid, set())
            if cat_uid in cats:
                context_uids.add(char_uid)

        # PerformanceDataset → OperatingPoint → Metric:
        # 只取该 Reaction 的 PerformanceDataset，且 Metric 关联该 Catalyst
        for perf_uid in rxn_to_perfs.get(rxn_uid, set()):
            context_uids.add(perf_uid)
            for op_uid in perf_to_ops.get(perf_uid, set()):
                for m_uid in op_to_metrics.get(op_uid, set()):
                    if metric_to_cat.get(m_uid) == cat_uid and metric_to_rxn.get(m_uid) == rxn_uid:
                        context_uids.add(op_uid)
                        context_uids.add(m_uid)

        # MechanisticClaim: APPLIES_TO_CATALYST 包含该 Catalyst 且 ABOUT_REACTION 包含该 Reaction
        for claim_uid in paper_claims.get(paper_uid, set()):
            cats = claim_to_cats.get(claim_uid, set())
            rxns = claim_to_rxns.get(claim_uid, set())
            if cat_uid in cats and rxn_uid in rxns:
                context_uids.add(claim_uid)
                # 该 claim 下的 EvidenceItem 也加入上下文
                context_uids.update(claim_to_evidence.get(claim_uid, set()))

        # 收集上下文中所有本体标签
        onto_tags = _collect_onto_tags(context_uids)
        if len(onto_tags) < 2:
            continue

        # 做有向共现
        onto_list = sorted(onto_tags)
        for i in range(len(onto_list)):
            type_i = onto_type_map.get(onto_list[i], "")
            if not type_i:
                continue
            for j in range(i + 1, len(onto_list)):
                type_j = onto_type_map.get(onto_list[j], "")
                if not type_j:
                    continue

                lookup = _PAIR_LOOKUP.get((type_i, type_j))
                if not lookup:
                    continue
                src_type, tgt_type, edge_type = lookup

                # 确定有向性：onto 的 type 对应 src/tgt
                if type_i == src_type and type_j == tgt_type:
                    key = (onto_list[i], onto_list[j], edge_type)
                elif type_j == src_type and type_i == tgt_type:
                    key = (onto_list[j], onto_list[i], edge_type)
                else:
                    continue

                co_occur[key]["count"] += 1
                co_occur[key]["papers"].add(paper_uid)
                if year:
                    co_occur[key]["years"].append(year)

    # ---- 3. 生成边 ----
    co_edges = []
    for (uid_src, uid_tgt, edge_type), info in co_occur.items():
        years = sorted(info["years"])
        co_edges.append({
            "source": uid_src,
            "target": uid_tgt,
            "edge_type": edge_type,
            "co_occurrence_count": info["count"],
            "witness_paper_count": len(info["papers"]),
            "witness_papers": sorted(info["papers"]),
            "first_year": years[0] if years else None,
            "last_year": years[-1] if years else None,
        })

    return co_edges


# ===== 4b: 规范化实体间的共研边 =====

def build_template_family_edges(
    all_nodes: list[dict], all_edges: list[dict]
) -> list[dict]:
    """CatalystFamily --TESTED_IN_TEMPLATE--> ReactionTemplate"""

    # Catalyst → CatalystFamily
    cat_to_family = {}
    for e in all_edges:
        if e["edge_type"] == "INSTANCE_OF_FAMILY":
            cat_to_family[e["source"]] = e["target"]

    # Reaction → ReactionTemplate
    rxn_to_template = {}
    for e in all_edges:
        if e["edge_type"] == "INSTANCE_OF_TEMPLATE":
            rxn_to_template[e["source"]] = e["target"]

    # Catalyst --TESTED_IN--> Reaction → 提升为 Family --TESTED_IN_TEMPLATE--> Template
    pair_witnesses = defaultdict(lambda: {"count": 0, "papers": set()})
    uid_to_node = {n["uid"]: n for n in all_nodes}

    for e in all_edges:
        if e["edge_type"] == "TESTED_IN":
            cat_uid = e["source"]
            rxn_uid = e["target"]
            fam_uid = cat_to_family.get(cat_uid)
            tmpl_uid = rxn_to_template.get(rxn_uid)
            if fam_uid and tmpl_uid:
                key = (fam_uid, tmpl_uid)
                pair_witnesses[key]["count"] += 1
                # 提取 paper
                doi_norm = cat_uid.split(":")[1]
                pair_witnesses[key]["papers"].add(f"paper:{doi_norm}")

    edges = []
    for (fam_uid, tmpl_uid), info in pair_witnesses.items():
        edges.append({
            "source": fam_uid,
            "target": tmpl_uid,
            "edge_type": "TESTED_IN_TEMPLATE",
            "witness_count": info["count"],
            "witness_paper_count": len(info["papers"]),
            "witness_papers": sorted(info["papers"]),
        })

    return edges


# ===== 4c: 相似度边 =====

def build_similarity_edges(all_nodes: list[dict]) -> list[dict]:
    """在 ReactionTemplate 之间和 CatalystFamily 之间建立 SIMILAR_TO 边"""
    edges = []

    # --- ReactionTemplate SIMILAR_TO ---
    templates = [n for n in all_nodes if n["node_type"] == "ReactionTemplate"]
    for i in range(len(templates)):
        for j in range(i + 1, len(templates)):
            ti, tj = templates[i], templates[j]
            # 相同 domain + 相同 class = 相似
            same_domain = (ti.get("reaction_domain") == tj.get("reaction_domain")
                          and ti.get("reaction_domain"))
            same_class = (ti.get("reaction_class") == tj.get("reaction_class")
                         and ti.get("reaction_class"))
            # reactants 交集
            ri = set(r.lower().strip() for r in ti.get("reactants", []) if r)
            rj = set(r.lower().strip() for r in tj.get("reactants", []) if r)
            reactant_overlap = len(ri & rj) / max(len(ri | rj), 1) if (ri or rj) else 0

            if same_domain and (same_class or reactant_overlap > 0.3):
                basis = []
                if same_domain: basis.append("domain")
                if same_class: basis.append("class")
                if reactant_overlap > 0: basis.append(f"reactant_jaccard={reactant_overlap:.2f}")
                edges.append({
                    "source": ti["uid"],
                    "target": tj["uid"],
                    "edge_type": "SIMILAR_TO",
                    "similarity_basis": basis,
                })

    # --- CatalystFamily SIMILAR_TO ---
    # 过于宽泛的 platform 不单独作为相似依据
    _COMMON_PLATFORMS = {
        "supported_metal_nanoparticles", "metal_oxides_hydroxides_oxyhydroxides",
        "composites_heterostructures", "other",
    }
    families = [n for n in all_nodes if n["node_type"] == "CatalystFamily"]
    for i in range(len(families)):
        for j in range(i + 1, len(families)):
            fi, fj = families[i], families[j]
            pi = set(fi.get("dominant_material_platform", []))
            pj = set(fj.get("dominant_material_platform", []))
            si = set(fi.get("dominant_active_site_form", []))
            sj = set(fj.get("dominant_active_site_form", []))

            # 去除宽泛标签后的交集
            specific_overlap = (pi & pj) - _COMMON_PLATFORMS
            site_overlap = (si & sj) if (si and sj) else set()

            # 需要同时满足：platform（非宽泛）+ site_form 重叠
            if specific_overlap and site_overlap:
                edges.append({
                    "source": fi["uid"],
                    "target": fj["uid"],
                    "edge_type": "SIMILAR_TO",
                    "similarity_basis": ["material_platform", "active_site_form"],
                })
            # 或者有具体 platform 重叠（非宽泛）
            elif specific_overlap:
                edges.append({
                    "source": fi["uid"],
                    "target": fj["uid"],
                    "edge_type": "SIMILAR_TO",
                    "similarity_basis": ["specific_material_platform"],
                })

    return edges
