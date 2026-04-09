"""Phase 3a: ReactionTemplate 归并 —— 把不同论文中的'同一类反应'归到同一个模板"""
from collections import defaultdict


def _normalize_species(species_list: list) -> tuple:
    """归一化物种列表：小写、去空格、排序、合并常见别名"""
    _ALIASES = {
        "h2": "H2", "hydrogen": "H2", "h₂": "H2",
        "co": "CO", "carbon monoxide": "CO",
        "co2": "CO2", "carbon dioxide": "CO2", "co₂": "CO2",
        "h2o": "H2O", "water": "H2O", "steam": "H2O",
        "ch4": "CH4", "methane": "CH4",
        "ch3oh": "CH3OH", "methanol": "CH3OH",
        "o2": "O2", "oxygen": "O2",
        "n2": "N2", "nitrogen": "N2",
        "nh3": "NH3", "ammonia": "NH3",
        "no": "NO", "no2": "NO2", "nox": "NOx",
    }
    result = set()
    for s in species_list:
        if not s:
            continue
        s_clean = s.strip().lower()
        result.add(_ALIASES.get(s_clean, s_clean))
    return tuple(sorted(result))


def _make_rxn_key(node: dict) -> str:
    """生成反应归并 key，避免只靠 family 标签造成明显过度合并"""
    families = tuple(sorted(f.strip().lower() for f in node.get("reaction_family", []) if f))
    domain = node.get("reaction_domain", "").strip().lower() or "unknown"
    rclass = node.get("reaction_class", "").strip().lower() or "unknown"
    reactants = _normalize_species(node.get("reactants", []))
    products = _normalize_species(node.get("target_products", []))

    if reactants or products:
        reactant_key = "|".join(reactants) if reactants else "unknown"
        product_key = "|".join(products) if products else "unknown"
        family_key = "|".join(families) if families else "unknown"
        return f"{domain}||{rclass}||{family_key}||R:{reactant_key}||P:{product_key}"

    transformation = node.get("transformation", "").strip().lower()
    name = node.get("reaction_name_reported", "").strip().lower()
    fallback = transformation or name or "unknown"
    family_key = "|".join(families) if families else "unknown"
    return f"{domain}||{rclass}||{family_key}||T:{fallback[:120]}"


def build_reaction_templates(instance_nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    rxn_nodes = [n for n in instance_nodes if n["node_type"] == "Reaction"]

    # 按 key 聚类
    clusters = defaultdict(list)
    for r in rxn_nodes:
        key = _make_rxn_key(r)
        clusters[key].append(r)

    template_nodes = []
    edges = []
    template_id = 0

    for key, members in clusters.items():
        template_id += 1
        # 取第一个成员的名字作为模板名
        rep = members[0]
        families = rep.get("reaction_family", [])
        family_str = "_".join(sorted(f.strip() for f in families if f)) if families else "unknown"

        t_uid = f"rxn_template:RT{template_id}"
        template_nodes.append({
            "uid": t_uid,
            "node_type": "ReactionTemplate",
            "template_name": rep.get("reaction_name_reported", ""),
            "reaction_domain": rep.get("reaction_domain", ""),
            "reaction_class": rep.get("reaction_class", ""),
            "reaction_family": rep.get("reaction_family", []),
            "reactants": rep.get("reactants", []),
            "target_products": rep.get("target_products", []),
            "instance_count": len(members),
            "merge_key": key,
            "family_label": family_str,
        })

        # 每个 Reaction 实例 → 对应 Template
        for m in members:
            edges.append({
                "source": m["uid"],
                "target": t_uid,
                "edge_type": "INSTANCE_OF_TEMPLATE",
            })

    return template_nodes, edges
