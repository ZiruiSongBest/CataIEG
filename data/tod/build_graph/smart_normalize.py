"""增强版规则归一化 —— 不需要 LLM，通过分析 369 个催化剂名称的模式来实现更好的归并
输出 catalyst_family_result.json 供 phase3b 消费。

用法: python smart_normalize.py
"""
import json
import re
import os
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "graph_output" / "catalyst_names_for_llm.json"
OUTPUT_PATH = BASE_DIR / "graph_output" / "catalyst_family_result.json"


# ===== 载体别名 =====
_SUPPORT_ALIASES = {
    "al2o3": "Al2O3", "alumina": "Al2O3", "γ-al2o3": "Al2O3",
    "gamma-al2o3": "Al2O3", "δ-al2o3": "Al2O3", "alpha-al2o3": "Al2O3",
    "α-al2o3": "Al2O3", "pseudo-boehmite": "Al2O3",
    "γ-alumina": "Al2O3", "γ-alumina (pseudo-boehmite)": "Al2O3",
    "sio2": "SiO2", "silica": "SiO2", "silica gel": "SiO2",
    "tio2": "TiO2", "titania": "TiO2",
    "zro2": "ZrO2", "zirconia": "ZrO2",
    "ceo2": "CeO2", "ceria": "CeO2",
    "mgo": "MgO", "magnesia": "MgO",
    "zno": "ZnO",
    "c": "C", "carbon": "C", "activated carbon": "C", "ac": "C",
    "carbon black": "C",
    "cnt": "CNT", "carbon nanotube": "CNT", "carbon nanotubes": "CNT",
    "carbon nanotubes (cnts)": "CNT",
    "graphene": "graphene",
    "zeolite": "zeolite",
    "ni foam": "Ni-foam",
    "carbon cloth": "carbon-cloth",
    "biochar": "biochar",
}

# ===== 无催化剂标识 =====
_NO_CATALYST = {
    "no catalyst", "uncatalyzed", "uncatalyzed condition", "non-catalytic",
    "absence of the catalyst", "blank", "blank test without catalyst",
    "none catalyst", "no catalyst used", "thermal cracking without catalyst",
    "non-catalytic thermal cracking",
}

# ===== 形貌后缀（去除） =====
_MORPHOLOGY_RE = re.compile(
    r'[\s\-_](?:nano(?:rod|wire|sheet|tube|flower|particle|frame|cube|sphere|crystal)s?'
    r'|rod|sphere|cube|wire|sheet|tube|flower|star|plate|film|foam|fiber|needle'
    r'|hollow|porous|mesoporous|core[\.\-]shell|yolk[\.\-]shell'
    r'|multiple[\-\s]pin|external[\-\s]branch'
    r'|pellet|powder|granule|bead|monolith|crushed|extruded|ground)s?\b',
    re.I
)

# ===== 载量前缀（去除） =====
_LOADING_RE = re.compile(
    r'^\d+[\.\d]*\s*(?:wt|mol|at|vol)?\.?\s*%?\s*[-–]?\s*', re.I
)

# ===== 前缀修饰词（去除） =====
_PREFIX_STRIP = re.compile(
    r'^(?:pre[\-\s]?sulph?ided|bare|raw|fresh|spent|calcined|reduced|dried'
    r'|wet|dry|nano|commercial|industrial)\s+',
    re.I
)


def _normalize_support(support: str) -> str:
    """归一化载体名称"""
    if not support:
        return ""
    s = support.strip().lower()
    # 去掉括号内的详细描述
    s = re.sub(r'\([^)]*\)', '', s).strip()
    # 去掉描述性前缀
    s = re.sub(r'^(?:γ|α|β|delta|gamma|alpha|beta)-', '', s)
    # 查表
    return _SUPPORT_ALIASES.get(s, s)


def normalize_catalyst(name: str, support: str, platforms: list[str]) -> str:
    """智能归一化催化剂名称"""
    name_orig = name.strip()
    name_lower = name_orig.lower()

    # 1. 无催化剂
    if name_lower in _NO_CATALYST or name_lower.startswith("no "):
        return "__no_catalyst__"
    if "without catalyst" in name_lower or "non-catalytic" in name_lower:
        return "__no_catalyst__"
    if name_lower in ("blank", "ap"):
        return "__no_catalyst__"

    # 2. 生物催化剂 → 属名
    if "bio_biocatalyst_immobilized" in platforms:
        # 提取属名
        genus_match = re.match(r'^([A-Z][a-z]+)', name_orig)
        if genus_match:
            genus = genus_match.group(1)
            # 细菌: Acidithiobacillus, Rhodococcus, Pseudomonas, Desulfovibrio, Brevibacterium
            species_match = re.match(r'^([A-Z][a-z]+\s+[a-z]+)', name_orig)
            if species_match:
                return species_match.group(1)
            return genus
        if "lipase" in name_lower:
            return "lipase"
        if "sludge" in name_lower:
            return "anaerobic-sludge"
        return name_orig

    # 3. 炭/焦类 → 按来源归类
    if "carbon_based" in platforms and not any(p in platforms for p in
        ["supported_metal_nanoparticles", "composites_heterostructures"]):
        if "co-pyrolysis" in name_lower or "co_pyrolysis" in name_lower:
            return "co-pyrolysis-char"
        if "char" in name_lower:
            if "oil shale" in name_lower or "oil shale" in support.lower():
                return "oil-shale-char"
            if "coal" in name_lower or "coal" in support.lower():
                return "coal-char"
            if "biomass" in name_lower:
                return "biomass-char"
            if "anthracite" in name_lower:
                return "coal-char"
            if "bituminous" in name_lower:
                return "coal-char"
            if "brown coal" in name_lower:
                return "coal-char"
            if "graphite" in name_lower:
                return "graphite-char"
            return "char"
        if "biochar" in name_lower:
            return "biochar"
        if "activated carbon" in name_lower:
            return "activated-carbon"
        if "coke" in name_lower:
            if "coal coke" in support.lower() or "coal coke" in name_lower:
                return "coal-coke"
            if "oil coke" in support.lower():
                return "oil-coke"
            return "coke"
        if "coal" in name_lower:
            return "coal"
        if "carbon" in name_lower:
            return "carbon"

    # 4. Amberlyst / 离子交换树脂
    amb_match = re.match(r'(?:crushed|wet|dry|ground)?\s*amberlyst\s*(\d+)', name_lower)
    if amb_match:
        return f"Amberlyst-{amb_match.group(1)}"
    if "amberlyte" in name_lower or "amberlite" in name_lower:
        ion_match = re.match(r'amberly[ti]e?\s+([\w\d]+)', name_lower)
        return f"Amberlite-{ion_match.group(1).upper()}" if ion_match else "Amberlite"
    if "dowex" in name_lower:
        dw_match = re.match(r'dowex\s+([\w\d]+)', name_lower)
        return f"Dowex-{dw_match.group(1)}" if dw_match else "Dowex"
    if "nafion" in name_lower:
        return "Nafion"

    # 5. 蒙脱土修饰
    if "montmorillonite" in name_lower:
        metal_match = re.search(r'modified with\s+(\w+)', name_lower)
        if metal_match:
            metal = metal_match.group(1).capitalize()
            return f"{metal}/montmorillonite"
        return "montmorillonite"

    # 6. 纯氧化物 / 矿物
    if name_lower in ("cao", "mgo", "al2o3", "tio2", "sio2", "zro2", "ceo2",
                       "zno", "fe2o3", "fe3o4", "cr2o3", "mno2", "cuo", "cu2o"):
        return name_orig.replace("γ-", "").replace("α-", "").replace("β-", "")
    if name_lower == "dolomite":
        return "dolomite"
    if name_lower == "calcined olivine" or name_lower == "olivine":
        return "olivine"
    if "hydrated lime" in name_lower or name_lower == "ca(oh)2":
        return "Ca(OH)2"
    if "quartz" in name_lower:
        return "quartz"
    if name_lower in ("pellets", "calcium in flyash", "flyash"):
        return "flyash" if "flyash" in name_lower or "fly ash" in name_lower else name_orig

    # 7. 去除前缀修饰词
    cleaned = name_orig
    cleaned = _PREFIX_STRIP.sub('', cleaned)

    # 8. 去除载量前缀
    cleaned = _LOADING_RE.sub('', cleaned)

    # 9. 去除形貌后缀
    cleaned = _MORPHOLOGY_RE.sub('', cleaned)

    # 10. 去除 " catalyst" 后缀
    cleaned = re.sub(r'\s+catalyst$', '', cleaned, flags=re.I)

    # 11. 处理 "X/Y" 格式
    slash_match = re.match(r'^([^/]+)/(.+)$', cleaned)
    if slash_match:
        active = slash_match.group(1).strip()
        sup_in_name = slash_match.group(2).strip()
        # 去掉载量
        active = _LOADING_RE.sub('', active)
        # 归一化载体
        sup_norm = _normalize_support(sup_in_name)
        if not sup_norm:
            sup_norm = sup_in_name
        return f"{active}/{sup_norm}"

    # 12. 处理 "X on Y" / "X supported on Y" 格式
    on_match = re.search(r'^(.+?)\s+(?:supported\s+)?on\s+(.+)$', cleaned, re.I)
    if on_match:
        active = on_match.group(1).strip()
        active = _LOADING_RE.sub('', active)
        sup = _normalize_support(on_match.group(2))
        return f"{active}/{sup}" if sup else active

    # 13. 处理 "X loaded on Y" 格式
    loaded_match = re.search(r'^(.+?)\s+loaded\s+on\s+(.+)$', cleaned, re.I)
    if loaded_match:
        active = loaded_match.group(1).strip()
        active = _LOADING_RE.sub('', active)
        sup = _normalize_support(loaded_match.group(2))
        return f"{active}/{sup}" if sup else active

    # 14. 如果有 support 字段但名称里没有 /
    sup_norm = _normalize_support(support)
    if sup_norm and "/" not in cleaned:
        # 检查名称本身不是 support
        if cleaned.lower().replace("γ-", "").replace("α-", "") != sup_norm.lower():
            return f"{cleaned}/{sup_norm}"

    # 15. 系列编号归一化 (如 0.3-FeNiAl, 0.5-FeNiAl → FeNiAl)
    series_match = re.match(r'^[\d\.]+[\-–]([A-Za-z][\w\-]+)', cleaned)
    if series_match:
        return series_match.group(1)

    # 16. NiHT 系列 (10NiHT, 20NiHT → NiHT)
    niht_match = re.match(r'^\d+([A-Z][a-z]*HT)', cleaned)
    if niht_match:
        return niht_match.group(1)

    # 17. 制备溶剂变体 CuZnAl-1.5(H2O) → CuZnAl
    prep_match = re.match(r'^([A-Za-z]+[\-\d\.]*)\([\w\-]+\)$', cleaned)
    if prep_match:
        base = prep_match.group(1)
        # 去掉末尾的 -数字
        base = re.sub(r'[\-\.]\d+[\.\d]*$', '', base)
        return base

    # 18. CuZnAl-数字 → CuZnAl
    ratio_match = re.match(r'^([A-Za-z]{2,})[\-\.]\d+[\.\d]*$', cleaned)
    if ratio_match:
        return ratio_match.group(1)

    # 19. 编码式名称 (cat-00-20-33-0) → 保留但加 support
    if re.match(r'^cat-\d', cleaned.lower()):
        if sup_norm:
            return f"cat-series/{sup_norm}"
        return cleaned

    # 20. Ce(x)-Zr(y)-Al(z)-FeOx 系列 → CeZrAlFeOx
    cezr_match = re.match(r'^[A-Z][a-z]?\(\d+[\.\d]*\)[\-–]', cleaned)
    if cezr_match:
        # 提取所有元素
        elements = re.findall(r'([A-Z][a-z]?)\(?', cleaned)
        return "".join(elements) + "Ox"

    # 21. 去掉描述性标签 (如 "spent catalyst sample A")
    if re.match(r'^(?:spent|fresh|used)\s+catalyst\s+sample', cleaned, re.I):
        if sup_norm:
            return f"spent-catalyst/{sup_norm}"
        return "spent-catalyst"
    if re.match(r'^catalyst\s+[A-Z]$', cleaned):
        if sup_norm:
            return f"catalyst-series/{sup_norm}"
        return cleaned

    # 22. Zeolite 归一化
    if "zeolites_molecular_sieves" in platforms:
        zeo = cleaned.upper()
        if "ZSM-5" in zeo or "ZSM5" in zeo:
            if "H" in zeo or "HZSM" in zeo:
                return "HZSM-5"
            return "ZSM-5"
        if "USY" in zeo:
            return "USY"
        if zeo == "Y" or "DEAL-Y" in zeo or "DEALY" in zeo:
            return "deAl-Y"
        if "ZEOLITE" in zeo:
            return "zeolite"

    # 23. Fe/ZSM-5 系列
    fe_zsm = re.match(r'^[\d\.]+%?\s*Fe/ZSM[\-]?5', cleaned)
    if fe_zsm:
        return "Fe/ZSM-5"

    # 24. NiMo 系列
    if "nimo" in cleaned.lower().replace(" ", "").replace("-", ""):
        if "al2o3" in cleaned.lower() or "al2o3" in support.lower():
            return "NiMo/Al2O3"

    # 25. 最终 fallback：清理后的名称
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = name_orig.strip()

    return cleaned


def post_normalize(canonical: str) -> str:
    """最终后处理：统一大小写、去除残余问题"""
    cn = canonical.strip()

    # 去掉 Greek 前缀
    cn = re.sub(r'^[γαβδ]-', '', cn)

    # Fe2O3-温度 → Fe2O3
    cn = re.sub(r'^(Fe2O3|Fe3O4|CeO2|TiO2|ZrO2|Al2O3|MgO|ZnO|CuO|NiO|MnO2|Mn2O3|Mn3O4)[\-–]\d{3,4}$', r'\1', cn)

    # 载体归一化（support 部分大小写统一）
    if "/" in cn:
        parts = cn.split("/", 1)
        active = parts[0]
        sup = parts[1]
        # 统一 ZSM-5 大小写
        sup = re.sub(r'(?i)zsm[\-]?5', 'ZSM-5', sup)
        sup = re.sub(r'(?i)^al2o3$', 'Al2O3', sup)
        sup = re.sub(r'(?i)^sio2$', 'SiO2', sup)
        sup = re.sub(r'(?i)^tio2$', 'TiO2', sup)
        sup = re.sub(r'(?i)^zro2$', 'ZrO2', sup)
        sup = re.sub(r'(?i)^ceo2$', 'CeO2', sup)
        sup = re.sub(r'(?i)^cnt$', 'CNT', sup)
        sup = re.sub(r'(?i)^c$', 'C', sup)
        # 去掉 /zeolite 如果 active 本身就是沸石
        if sup.lower() == "zeolite" and re.match(r'(?i)H?ZSM|USY|deal|zeolite|mordenite|beta', active):
            return active
        # 去掉 /support 中的描述性内容
        sup = re.sub(r'(?i)ordered mesoporous alumina', 'Al2O3', sup)
        sup = re.sub(r'(?i)ni,mg,al-mixed oxides from hydrotalcite', 'HT', sup)
        sup = re.sub(r'(?i)ni[\-\s]?foam', 'Ni-foam', sup)
        cn = f"{active}/{sup}"

    # ZSM → ZSM-5
    if cn == "ZSM":
        cn = "ZSM-5"
    if cn == "HZSM":
        cn = "HZSM-5"

    # Fe/zsm-5 → Fe/ZSM-5
    cn = re.sub(r'(?i)zsm[\-]?5', 'ZSM-5', cn)

    # NiHT → NiAl-HT (hydrotalcite)
    if re.match(r'^NiHT', cn):
        cn = re.sub(r'^NiHT', 'NiMgAl-HT', cn)

    return cn


def main():
    with open(INPUT_PATH) as f:
        catalysts = json.load(f)
    print(f"Loaded {len(catalysts)} catalysts")

    results = []
    for cat in catalysts:
        canonical = normalize_catalyst(
            cat["name_reported"],
            cat.get("substrate_or_support", ""),
            cat.get("labels_material_platform", []),
        )
        canonical = post_normalize(canonical)
        results.append({
            "uid": cat["uid"],
            "canonical_name": canonical,
        })

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 统计
    names = [r["canonical_name"] for r in results]
    unique_names = set(names)
    name_counts = Counter(names)

    print(f"\nResults:")
    print(f"  Total catalysts: {len(results)}")
    print(f"  Unique canonical names: {len(unique_names)}")
    print(f"  Compression: {len(results)}/{len(unique_names)} = {len(results)/len(unique_names):.1f}x")
    singletons = sum(1 for c in name_counts.values() if c == 1)
    print(f"  Singletons: {singletons} ({singletons/len(unique_names)*100:.0f}%)")

    print(f"\nTop merged families:")
    for name, count in name_counts.most_common(25):
        print(f"  {count:3d}x  {name}")

    print(f"\nSample singletons:")
    singles = [n for n, c in name_counts.items() if c == 1]
    for s in sorted(singles)[:20]:
        print(f"  {s}")

    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
