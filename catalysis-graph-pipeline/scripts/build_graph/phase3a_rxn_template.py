"""Phase 3a: ReactionTemplate 归并 —— 基于 LLM 归一化的 canonical_reaction_name 聚类。

流程：
  1. 导出所有 Reaction 节点的字段到 reaction_names_for_llm.json（供离线 LLM 使用）
  2. 若已有 reaction_template_result.json，则按 canonical_reaction_name 聚类
  3. 否则回退到基于 domain/class/family/reactants/products 的字符串匹配聚类
"""
import json
import os
import re
from collections import defaultdict

from config import RXN_NAMES_FOR_LLM, RXN_TEMPLATE_RESULT


# ===== Fallback: 字符串匹配聚类（用在未有 LLM 结果时） =====

def _normalize_species(species_list: list) -> tuple:
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


def _fallback_key(node: dict) -> str:
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


# ===== LLM canonical 清洗 =====

def _sanitize_canonical(canonical: str) -> str:
    """轻量清洗 LLM 输出：去首尾空格、压缩多空格、小写归一（保留专有缩写）。"""
    if not canonical:
        return ""
    s = re.sub(r"\s+", " ", canonical).strip()
    # 归一常见缩写大小写变体
    _UPPER_TOKENS = {
        "oer", "orr", "her", "co2rr", "nh3", "no2", "nox", "co2",
        "co", "f-t", "scr", "voc", "sox", "so2",
    }
    parts = s.split(" ")
    normalized = []
    for p in parts:
        low = p.lower()
        if low in _UPPER_TOKENS:
            normalized.append(low.upper() if low not in {"co2rr", "co2", "nh3", "no2", "nox", "so2"} else p.upper().replace("CO2RR", "CO2RR"))
        else:
            normalized.append(p)
    return " ".join(normalized).strip().lower() if len(normalized) == 0 else s


def _export_for_llm(rxn_nodes: list[dict], output_path: str):
    items = []
    for r in rxn_nodes:
        items.append({
            "uid": r["uid"],
            "reaction_name_reported": r.get("reaction_name_reported", ""),
            "reaction_domain": r.get("reaction_domain", ""),
            "reaction_class": r.get("reaction_class", ""),
            "reaction_family": r.get("reaction_family", []),
            "transformation": r.get("transformation", ""),
            "reactants": r.get("reactants", []),
            "target_products": r.get("target_products", []),
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return items


def build_reaction_templates(instance_nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    rxn_nodes = [n for n in instance_nodes if n["node_type"] == "Reaction"]

    # 无论如何都导出 LLM 输入（方便下次重跑）
    _export_for_llm(rxn_nodes, RXN_NAMES_FOR_LLM)

    uid_to_canonical = {}
    uid_to_aliases = {}
    if os.path.exists(RXN_TEMPLATE_RESULT):
        with open(RXN_TEMPLATE_RESULT, "r", encoding="utf-8") as f:
            llm_results = json.load(f)
        for item in llm_results:
            name = (item.get("canonical_reaction_name") or "").strip()
            if name:
                uid_to_canonical[item["uid"]] = _sanitize_canonical(name)
                uid_to_aliases[item["uid"]] = item.get("canonical_reaction_aliases", [])
        print(f"  使用 LLM 归一化结果: {len(uid_to_canonical)} 条")
    else:
        print(f"  LLM 结果文件不存在（{RXN_TEMPLATE_RESULT}），使用字符串匹配 fallback")
        print(f"  已导出 LLM 输入: {RXN_NAMES_FOR_LLM}")

    # 聚类
    clusters = defaultdict(list)
    for r in rxn_nodes:
        canonical = uid_to_canonical.get(r["uid"])
        if canonical:
            key = f"llm:{canonical.lower()}"
        else:
            key = f"rule:{_fallback_key(r)}"
        clusters[key].append(r)

    template_nodes = []
    edges = []
    template_id = 0

    for key, members in clusters.items():
        template_id += 1
        rep = members[0]

        # 以 LLM canonical_reaction_name 为模板名；fallback 时取第一个成员的 reported 名
        if key.startswith("llm:"):
            canonical_name = uid_to_canonical[rep["uid"]]
            # 汇总该模板下所有成员的 aliases（去重）
            all_aliases = set()
            for m in members:
                for a in uid_to_aliases.get(m["uid"], []):
                    if a and a.strip():
                        all_aliases.add(a.strip())
            aliases = sorted(all_aliases)
            source_tag = "llm"
        else:
            canonical_name = rep.get("reaction_name_reported", "") or rep.get("transformation", "") or "unknown"
            aliases = []
            source_tag = "rule"

        families = rep.get("reaction_family", [])
        family_str = "_".join(sorted(f.strip() for f in families if f)) if families else "unknown"

        t_uid = f"rxn_template:RT{template_id}"
        template_nodes.append({
            "uid": t_uid,
            "node_type": "ReactionTemplate",
            "template_name": canonical_name,
            "canonical_aliases": aliases,
            "reaction_domain": rep.get("reaction_domain", ""),
            "reaction_class": rep.get("reaction_class", ""),
            "reaction_family": rep.get("reaction_family", []),
            "reactants": rep.get("reactants", []),
            "target_products": rep.get("target_products", []),
            "instance_count": len(members),
            "merge_key": key,
            "merge_source": source_tag,
            "family_label": family_str,
        })

        for m in members:
            edges.append({
                "source": m["uid"],
                "target": t_uid,
                "edge_type": "INSTANCE_OF_TEMPLATE",
            })

    return template_nodes, edges
