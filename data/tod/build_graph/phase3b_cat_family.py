"""Phase 3b: CatalystFamily 归并
先导出 richer LLM 输入，再消费已有 LLM 结果。
如果没有 LLM 结果，就使用更保守的规则 fallback。
"""
import json
import os
import re
from collections import Counter, defaultdict

from config import CAT_FAMILY_RESULT, CAT_NAMES_FOR_LLM


_SUPPORT_ALIASES = {
    "al2o3": "Al2O3",
    "alumina": "Al2O3",
    "gamma-al2o3": "Al2O3",
    "gamma alumina": "Al2O3",
    "γ-al2o3": "Al2O3",
    "gamma-alumina": "Al2O3",
    "sio2": "SiO2",
    "silica": "SiO2",
    "tio2": "TiO2",
    "titania": "TiO2",
    "zro2": "ZrO2",
    "zirconia": "ZrO2",
    "ceo2": "CeO2",
    "ceria": "CeO2",
    "mgo": "MgO",
    "magnesia": "MgO",
    "zno": "ZnO",
    "zeolite": "zeolite",
}

_GENERIC_CARBON_LABELS = {"c", "carbon", "char", "carbon support"}
_GENERIC_CARBON_SUPPORTS = {"c", "carbon", "char"}
_BROAD_CARBON_CANONICALS = {
    "coal",
    "coke",
    "biochar",
    "co-pyrolysis-char",
    "co-pyrolysis char",
    "ni/char",
}
_CONTROL_PATTERNS = [
    re.compile(
        r"^(?:no catalyst|without catalyst|absence of(?: the)? catalyst|"
        r"uncatalyzed(?: condition)?|non-catalytic(?: condition)?|"
        r"blank test without catalyst|control without catalyst|none)$",
        re.I,
    ),
]


def _clean_text(text: str) -> str:
    return " ".join(str(text).split()).strip()


def _normalize_active_text(text: str) -> str:
    text = _clean_text(text)
    text = re.sub(r"^\d+(?:\.\d+)?\s*(?:wt|mol|at|vol)?\.?\s*%?\s*", "", text, flags=re.I)
    text = re.sub(
        r"[\-_\s](?:rod|sphere|cube|wire|sheet|tube|flower|star|plate|film|foam|fiber|needle|"
        r"hollow|porous|mesoporous|core\.shell|yolk\.shell)s?\b",
        "",
        text,
        flags=re.I,
    )
    return _clean_text(text)


def _normalize_support_name(support: str) -> str:
    support = _clean_text(support)
    if not support:
        return ""

    lower = support.lower()
    de_greek = lower.replace("γ-", "").replace("α-", "").replace("β-", "")

    if "activated carbon" in lower or lower == "ac":
        return "activated carbon"
    if "carbon nanotube" in lower or "carbon nanotubes" in lower or lower == "cnt":
        return "CNT"
    if "graphene" in lower:
        return "graphene"
    if "cordierite" in lower and ("al2o3" in lower or "alumina" in lower):
        return "Al2O3-coated cordierite"
    if "cordierite monolith" in lower:
        return "cordierite monolith"
    if "cordierite" in lower:
        return "cordierite"
    if "ceramic honeycomb" in lower and ("al2o3" in lower or "alumina" in lower):
        return "Al2O3-coated ceramic honeycomb"
    if "calcium aluminate" in lower:
        return "calcium aluminate"
    if "montmorillonite" in lower:
        return "montmorillonite"
    if "sba-15" in lower and "zr" in lower:
        return "ZrO2-SBA-15"

    return _SUPPORT_ALIASES.get(de_greek, support)


def _normalize_control_name(node: dict) -> str:
    name = _clean_text(node.get("name_reported", ""))
    if any(pattern.match(name) for pattern in _CONTROL_PATTERNS):
        return "no_catalyst"
    return ""


def _extract_temperature_token(text: str) -> str:
    match = re.search(r"(\d{3,4})\s*(?:°|º)?\s*C\b", text, flags=re.I)
    if match:
        return f"{match.group(1)}C"
    return ""


def _carbon_variant(node: dict) -> str:
    variant_rule = _clean_text(node.get("variant_rule", "")).lower()
    variant_value = _clean_text(node.get("variant_value", ""))
    if "pyrolysis" in variant_rule or "carbonization" in variant_rule:
        token = _extract_temperature_token(variant_value)
        if token:
            return token

    name = _clean_text(node.get("name_reported", ""))
    direct = re.search(r"(?:de-)?char[-_ ]?(\d{3,4})\b", name, flags=re.I)
    if direct:
        return f"{direct.group(1)}C"

    return _extract_temperature_token(name) or _extract_temperature_token(" ".join(node.get("aliases", [])))


def _specific_carbon_material(node: dict) -> str:
    name = _clean_text(node.get("name_reported", ""))
    texts = [
        name,
        _clean_text(node.get("substrate_or_support", "")),
        _clean_text(node.get("series_name", "")),
        *[_clean_text(alias) for alias in node.get("aliases", [])],
    ]
    lower_fields = [text.lower() for text in texts if text]
    joined = " | ".join(lower_fields)
    if not joined:
        return ""

    base = ""
    name_lower = name.lower()
    if name_lower in {
        "raw coal",
        "edta-inhibited coal",
        "pyrolyzed coal",
        "biochar",
        "acid-washed biochar",
        "activated carbon",
        "coal char",
        "wheat straw char",
        "coke in the cracking zones",
    }:
        return name_lower
    if name_lower.startswith("co-pyrolysis char"):
        if "acid washed wheat straw" in name_lower:
            return "co-pyrolysis char from acid-washed wheat straw/coal"
        if "raw wheat straw" in name_lower:
            return "co-pyrolysis char from raw wheat straw/coal"
        variant = _carbon_variant(node)
        if variant:
            return f"co-pyrolysis char@{variant}"
        return "co-pyrolysis char"

    if any(field == "ac" or "activated carbon" in field for field in lower_fields):
        base = "activated carbon"
    elif "acid-washed biochar" in joined:
        base = "acid-washed biochar"
    elif "biochar" in joined:
        base = "biochar"
    elif "peat char activated by koh" in joined:
        base = "KOH-activated peat char"
    elif "peat char activated by co2" in joined:
        base = "CO2-activated peat char"
    elif "peat char" in joined:
        base = "peat char"
    elif any(field == "cnt" or "carbon nanotube" in field for field in lower_fields):
        base = "CNT"
    elif any("graphene" in field for field in lower_fields):
        base = "graphene"
    elif "carbon black" in joined:
        base = "carbon black"
    elif "carbon cloth" in joined:
        base = "carbon cloth"
    elif "unburned carbon" in joined or "fly ash" in joined or "flyash" in joined:
        base = "unburned carbon in fly ash"
    elif "coal coke" in joined:
        base = "coal coke"
    elif any(field == "coal" for field in lower_fields):
        base = "coal"
    elif "petroleum coke" in joined or "oil coke" in joined:
        base = "petroleum coke"
    elif "co-pyrolysis" in joined and "char" in joined:
        base = "co-pyrolysis char"
    elif "demineralized oil shale char" in joined or "de-char" in joined:
        base = "demineralized oil shale char"
    elif "oil shale char" in joined or re.search(r"\bchar-\d{3,4}\b", joined):
        base = "oil shale char"
    elif "brown coal" in joined and "char" in joined:
        base = "brown coal char"
    elif "bituminous coal" in joined and "char" in joined:
        base = "bituminous coal char"
    elif "anthracite" in joined and "char" in joined:
        base = "anthracite char"
    elif "biomass" in joined and "char" in joined:
        base = "biomass char"
    elif "coal" in joined and "char" in joined:
        base = "coal char"
    elif re.search(r"\bchar\b", joined):
        base = "char"
    elif re.search(r"\bcoke\b", joined):
        base = "coke"

    if base and "char" in base:
        variant = _carbon_variant(node)
        if variant:
            base = f"{base}@{variant}"

    return base


def _split_canonical_name(canonical: str) -> tuple[str, str]:
    if "/" not in canonical:
        return canonical, ""
    active, support = canonical.split("/", 1)
    return _clean_text(active), _clean_text(support)


def _should_replace_support(current_support: str, raw_support: str) -> bool:
    current_support = _clean_text(current_support)
    raw_support = _clean_text(raw_support)
    if not raw_support:
        return False
    if not current_support:
        return True
    if _normalize_support_name(current_support).lower() == _normalize_support_name(raw_support).lower():
        return False
    if current_support.lower() in _GENERIC_CARBON_SUPPORTS:
        return True
    if current_support == "Al2O3" and raw_support in {
        "calcium aluminate",
        "cordierite",
        "cordierite monolith",
        "Al2O3-coated cordierite",
        "Al2O3-coated ceramic honeycomb",
    }:
        return True
    return False


def _rule_normalize(node: dict) -> str:
    control = _normalize_control_name(node)
    if control:
        return control

    carbon_material = _specific_carbon_material(node)
    name = _normalize_active_text(node.get("name_reported", ""))
    raw_support = _normalize_support_name(node.get("substrate_or_support", ""))

    if "/" in name:
        active, support = _split_canonical_name(name)
        support = _normalize_support_name(support) or raw_support or support
        return f"{active}/{support}" if support else active

    if carbon_material:
        return carbon_material

    if raw_support and name and name.lower() != raw_support.lower():
        if re.fullmatch(r"[A-Za-z0-9\-\+\.\(\)]+", name):
            return f"{name}/{raw_support}"

    return name or raw_support or "unknown"


def _sanitize_canonical_name(canonical: str, node: dict) -> str:
    control = _normalize_control_name(node)
    if control:
        return control

    canonical = _clean_text(canonical)
    if not canonical:
        canonical = _rule_normalize(node)

    if canonical.lower() in _GENERIC_CARBON_LABELS and "carbon_based" not in node.get("labels_material_platform", []):
        return _rule_normalize(node)

    # --- POST-LLM CHEMISTRY VALIDATION ---
    # Guard A: supported metal catalyst must not be collapsed to bare support name.
    # e.g. LLM returning "Al2O3" for a node with platform=supported_metal_nanoparticles is wrong.
    platforms = node.get("labels_material_platform", [])
    _BARE_SUPPORTS = {
        "al2o3", "sio2", "tio2", "zro2", "ceo2", "mgo", "zno",
        "activated carbon", "cnt", "graphene", "biochar", "zeolite",
    }
    if (canonical.lower() in _BARE_SUPPORTS
            and "supported_metal_nanoparticles" in platforms):
        # LLM likely confused the support with the catalyst — fall back to rule
        canonical = _rule_normalize(node)

    # Guard B: bulk oxide must not get a "Metal/Support" canonical when there is no
    # real support relationship (e.g. NiAl mixed oxide ≠ Ni/Al2O3).
    if ("/" in canonical
            and "supported_metal_nanoparticles" not in platforms
            and "metal_oxides_hydroxides_oxyhydroxides" in platforms):
        # Check if the name_reported suggests a supported catalyst
        name_lower = node.get("name_reported", "").lower()
        support_field = node.get("substrate_or_support", "").strip()
        # If there's no explicit support and no "/" in the original name, this is
        # likely a bulk mixed oxide that LLM incorrectly formatted as supported
        if not support_field and "/" not in name_lower:
            canonical = _rule_normalize(node)

    active, support = _split_canonical_name(canonical)
    carbon_material = _specific_carbon_material(node)
    raw_support = _normalize_support_name(node.get("substrate_or_support", ""))

    if carbon_material:
        if support and (
            support.lower() in _GENERIC_CARBON_SUPPORTS
            or support.lower() in _GENERIC_CARBON_LABELS
            or support.lower() in _BROAD_CARBON_CANONICALS
        ):
            return f"{active}/{carbon_material}"
        if not support and canonical.lower() != carbon_material.lower():
            return carbon_material
        if canonical.lower() in _GENERIC_CARBON_LABELS or canonical.lower() in _BROAD_CARBON_CANONICALS:
            return carbon_material

    if support and raw_support and _should_replace_support(support, raw_support):
        return f"{active}/{raw_support}"

    if support and raw_support in {"sand", "quartz", "quartz sand"} and "coprecipitated" in node.get("name_reported", "").lower():
        return _normalize_active_text(node.get("name_reported", ""))

    return canonical


def _export_for_llm(cat_nodes: list[dict], output_path: str):
    items = []
    for c in cat_nodes:
        items.append({
            "uid": c["uid"],
            "name_reported": c["name_reported"],
            "aliases": c.get("aliases", []),
            "role": c.get("role", ""),
            "series_name": c.get("series_name", ""),
            "variant_rule": c.get("variant_rule", ""),
            "variant_value": c.get("variant_value", ""),
            "substrate_or_support": c.get("substrate_or_support", ""),
            "labels_material_platform": c.get("labels_material_platform", []),
            "labels_active_site_form": c.get("labels_active_site_form", []),
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return items


def build_catalyst_families(instance_nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    cat_nodes = [n for n in instance_nodes if n["node_type"] == "Catalyst"]

    _export_for_llm(cat_nodes, CAT_NAMES_FOR_LLM)

    uid_to_canonical = {}
    if os.path.exists(CAT_FAMILY_RESULT):
        with open(CAT_FAMILY_RESULT, "r", encoding="utf-8") as f:
            llm_results = json.load(f)
        for item in llm_results:
            uid_to_canonical[item["uid"]] = item.get("canonical_name", "")
        print(f"  使用 LLM 归一化结果: {len(uid_to_canonical)} 条")
    else:
        print("  LLM 结果文件不存在，使用规则 fallback")
        print(f"  已导出 LLM 输入: {CAT_NAMES_FOR_LLM}")

    clusters = defaultdict(list)
    for c in cat_nodes:
        provisional = uid_to_canonical.get(c["uid"], "") or _rule_normalize(c)
        canonical = _sanitize_canonical_name(provisional, c)
        clusters[canonical].append(c)

    family_nodes = []
    edges = []
    fam_id = 0

    for canonical, members in clusters.items():
        fam_id += 1
        f_uid = f"cat_family:CF{fam_id}"

        platform_counts = Counter()
        site_counts = Counter()
        for m in members:
            for platform in m.get("labels_material_platform", []):
                if platform:
                    platform_counts[platform] += 1
            for site in m.get("labels_active_site_form", []):
                if site:
                    site_counts[site] += 1

        family_nodes.append({
            "uid": f_uid,
            "node_type": "CatalystFamily",
            "canonical_name": canonical,
            "instance_count": len(members),
            "member_uids": [m["uid"] for m in members],
            "dominant_material_platform": [p for p, _ in platform_counts.most_common(3)],
            "dominant_active_site_form": [s for s, _ in site_counts.most_common(3)],
        })

        for m in members:
            edges.append({
                "source": m["uid"],
                "target": f_uid,
                "edge_type": "INSTANCE_OF_FAMILY",
            })

    return family_nodes, edges
