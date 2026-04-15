"""二次归一：把 canonical_catalyst_family 列表送给 LLM 做 family-level 去重。

合并由首轮 LLM 在不同 batch 里产生的粒度不一致家族
（如 HZSM-5 / ZSM-5 zeolite / zeolite 应合并）。

输入：CAT_FAMILY_RESULT（首轮 LLM 结果）
输出：
  - <OUTPUT_DIR>/catalyst_family_dedup_map.json  —— 旧家族名 → 新家族名
  - 原地更新 CAT_FAMILY_RESULT（备份到 catalyst_family_result_before_dedup.json）
"""
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

from config import CAT_FAMILY_RESULT, OUTPUT_DIR
from llm_client import call_chat, parse_json_array, run_batches_parallel

BATCH_SIZE = int(os.environ.get("DEDUP_BATCH_SIZE", "120"))
MAP_OUTPUT = Path(OUTPUT_DIR) / "catalyst_family_dedup_map.json"
BACKUP_PATH = Path(OUTPUT_DIR) / "catalyst_family_result_before_dedup.json"


SYSTEM_PROMPT = """You are performing a SECOND-PASS deduplication of catalyst family names for a heterogeneous catalysis knowledge graph.

The first pass already normalized each catalyst to a canonical_catalyst_family name, but different batches may have used different granularities for the same material (e.g. one batch chose "HZSM-5", another "ZSM-5 zeolite", another "zeolite"). Your job is to MERGE families that refer to the SAME material entity, while KEEPING genuinely different materials SEPARATE.

MERGE RULES (apply in order)

RULE 1 — Same zeolite framework code = same family.
  "HZSM-5", "ZSM-5", "ZSM-5 zeolite", "nano-ZSM-5" -> all merge to "HZSM-5" (or the most specific acidic-form when explicit).
  Different framework codes (HZSM-5 vs USY vs Y vs Beta vs SAPO-34) stay SEPARATE.
  A pure umbrella label like "zeolite" is TOO GENERIC — if its members are clearly one specific framework, merge into that framework.

RULE 2 — Same bulk oxide / mixed oxide = same family.
  "Fe2O3", "α-Fe2O3", "hematite" -> "Fe2O3".
  "Al2O3", "γ-Al2O3", "alumina" -> "Al2O3".
  Different mixed oxide compositions stay separate: "CuZnAl" != "CuZn" != "ZnAl".

RULE 3 — Same supported-metal system = same family.
  "Pt/Al2O3", "Pt/γ-Al2O3", "Pt/alumina" -> "Pt/Al2O3".
  "Ni/Al2O3" != "NiMo/Al2O3" != "Mo/Al2O3" (active metal composition differs).
  "Ni/Al2O3" != "Ni/SiO2" (support differs).
  "Ni/Al2O3" != "Al2O3" (supported metal != bare support — NEVER merge).

RULE 4 — Consistent notation.
  Normalize support name: "alumina" -> "Al2O3", "silica" -> "SiO2", "titania" -> "TiO2", "ceria" -> "CeO2", "zirconia" -> "ZrO2".
  Drop crystal-phase prefixes (γ, α, β) at the family level.

RULE 5 — Do NOT merge across:
  - bare support vs supported metal
  - different active metals / different number of metals
  - different supports
  - biological vs chemical catalyst
  - carbon material types (activated carbon != CNT != biochar != coke != coal char)

RULE 6 — Conservative behavior.
  If unsure, KEEP SEPARATE.
  The final canonical should be one of the input family names (the most informative / standard one).

INPUT FORMAT
A JSON array of family records: [{"family": "HZSM-5", "members_sample": [...], "count": 6}, ...]

OUTPUT FORMAT
Return ONLY a JSON array mapping each input family to its canonical: [{"family": "...", "canonical": "..."}, ...]
Every input family MUST appear exactly once in the output. No explanation, no markdown fence."""


def build_user_prompt(records):
    return (
        f"Deduplicate these {len(records)} catalyst family names. "
        f"For each input family, return the canonical family it should merge into (can be itself).\n\n"
        f"INPUT:\n{json.dumps(records, ensure_ascii=False)}\n\n"
        f"Return a JSON array mapping every input family to its canonical family. Every family MUST appear exactly once."
    )


def process_batch(records):
    try:
        text = call_chat(SYSTEM_PROMPT, build_user_prompt(records))
        raw = parse_json_array(text)
    except Exception as exc:
        print(f"  [dedup batch {len(records)} items] failed: {exc}")
        return [{"family": r["family"], "canonical": r["family"]} for r in records]

    input_set = {r["family"] for r in records}
    seen = set()
    out = []
    for m in raw:
        fam = (m.get("family") or "").strip()
        canon = (m.get("canonical") or "").strip()
        if fam in input_set and canon and fam not in seen:
            seen.add(fam)
            out.append({"family": fam, "canonical": canon})
    # Fill in missing with identity
    for r in records:
        if r["family"] not in seen:
            out.append({"family": r["family"], "canonical": r["family"]})
    return out


def _resolve_transitive(mapping):
    def find(x, depth=0):
        if depth > 50:
            return x
        nxt = mapping.get(x, x)
        if nxt == x:
            return x
        return find(nxt, depth + 1)
    return {k: find(k) for k in mapping}


def main():
    with open(CAT_FAMILY_RESULT, "r", encoding="utf-8") as f:
        first_pass = json.load(f)
    print(f"[dedup] loaded {len(first_pass)} first-pass catalyst records")

    fam_to_members = defaultdict(list)
    for item in first_pass:
        fam = (item.get("canonical_catalyst_family") or item.get("canonical_name") or "").strip()
        if not fam:
            continue
        name = item.get("canonical_catalyst_name") or fam
        fam_to_members[fam].append(name)

    records = []
    for fam, members in fam_to_members.items():
        uniq = list(dict.fromkeys(members))
        records.append({"family": fam, "members_sample": uniq[:5], "count": len(members)})
    records.sort(key=lambda r: -r["count"])
    print(f"[dedup] unique families to dedup: {len(records)}")

    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    print(f"[dedup] {len(batches)} batches of ~{BATCH_SIZE}")

    def on_progress(done, total, _):
        print(f"  [dedup] {done}/{total} batches done")

    results = run_batches_parallel(batches, process_batch, progress_callback=on_progress, concurrency=min(4, len(batches)))

    mapping = {r["family"]: r["canonical"] for r in results}
    mapping = _resolve_transitive(mapping)

    merged = sum(1 for k, v in mapping.items() if k != v)
    unique_after = len(set(mapping.values()))
    print(f"\n[dedup] {len(mapping)} -> {unique_after} families (merged {merged})")

    with open(MAP_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    if not BACKUP_PATH.exists():
        shutil.copy(CAT_FAMILY_RESULT, BACKUP_PATH)
        print(f"[dedup] backup: {BACKUP_PATH}")

    updated = []
    for item in first_pass:
        new = dict(item)
        old = (item.get("canonical_catalyst_family") or item.get("canonical_name") or "").strip()
        if old and old in mapping:
            new["canonical_catalyst_family"] = mapping[old]
            new["canonical_name"] = mapping[old]
        updated.append(new)

    with open(CAT_FAMILY_RESULT, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    print(f"[dedup] updated {CAT_FAMILY_RESULT}")


if __name__ == "__main__":
    main()
