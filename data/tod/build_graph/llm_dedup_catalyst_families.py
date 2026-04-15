"""二次归一：把 canonical_catalyst_family 列表送给 LLM 做一轮 family-level 去重。

目的：解决首轮 LLM 在不同 batch 里对同一物质给出不同粒度 family 的问题
（例如 HZSM-5 vs "ZSM-5 zeolite" vs "zeolite" 应该合并为同一个家族）。

输入：graph_output/catalyst_family_result.json（首轮 LLM 结果）
输出：
  - graph_output/catalyst_family_dedup_map.json  —— 旧家族名 → 新家族名 的映射
  - 原地更新 catalyst_family_result.json 的 canonical_catalyst_family 字段（备份原文件）
"""
import json
import os
import re
import shutil
import time
import urllib.request
from collections import defaultdict
from pathlib import Path


BASE_URL = os.environ.get("CATALYST_LLM_BASE_URL", "https://api.bltcy.ai/v1")
API_KEY = os.environ.get("CATALYST_LLM_API_KEY") or os.environ.get("BLTCY_API_KEY")
MODEL = os.environ.get("CATALYST_LLM_MODEL", "claude-sonnet-4-6")
MAX_RETRIES = 3
RETRY_DELAY = 5
# 一次给 LLM 多少个 family（每个 family 附带 1–5 个成员样例）。全部 ~200 条，单批就能放下。
BATCH_SIZE = 120

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "graph_output" / "catalyst_family_result.json"
MAP_OUTPUT = BASE_DIR / "graph_output" / "catalyst_family_dedup_map.json"
BACKUP_PATH = BASE_DIR / "graph_output" / "catalyst_family_result_before_dedup.json"


SYSTEM_PROMPT = """You are performing a SECOND-PASS deduplication of catalyst family names for a heterogeneous catalysis knowledge graph.

The first pass already normalized each catalyst to a canonical_catalyst_family name, but different batches may have used different granularities for the same material (e.g. one batch chose "HZSM-5", another "ZSM-5 zeolite", another "zeolite"). Your job is to MERGE families that refer to the SAME material entity, while KEEPING genuinely different materials SEPARATE.

━━━ MERGE RULES (apply in order) ━━━

RULE 1 — Same zeolite framework code = same family.
  "HZSM-5", "ZSM-5", "ZSM-5 zeolite", "nano-ZSM-5" → all merge to "HZSM-5" (or the most specific acidic-form when explicit).
  Different framework codes (HZSM-5 vs USY vs Y vs Beta vs SAPO-34) stay SEPARATE.
  A pure umbrella label like "zeolite" is TOO GENERIC — if its members are clearly one specific framework, merge into that framework; if truly mixed, keep "zeolite".

RULE 2 — Same bulk oxide / mixed oxide = same family.
  "Fe2O3", "α-Fe2O3", "hematite" → "Fe2O3".
  "Al2O3", "γ-Al2O3", "alumina" → "Al2O3".
  Different mixed oxide compositions stay separate: "CuZnAl" ≠ "CuZn" ≠ "ZnAl".

RULE 3 — Same supported-metal system = same family.
  "Pt/Al2O3", "Pt/γ-Al2O3", "Pt/alumina" → "Pt/Al2O3".
  "Ni/Al2O3" ≠ "NiMo/Al2O3" ≠ "Mo/Al2O3" (active metal composition differs).
  "Ni/Al2O3" ≠ "Ni/SiO2" (support differs).
  "Ni/Al2O3" ≠ "Al2O3" (supported metal ≠ bare support — NEVER merge).

RULE 4 — Consistent notation.
  Alphabetize multi-metal tokens: "NiMo" = "MoNi" → use "MoNi" or "NiMo" consistently (prefer alphabetical: "MoNi").
  Normalize support name to the chemical formula: "alumina" → "Al2O3", "silica" → "SiO2", "titania" → "TiO2", "ceria" → "CeO2", "zirconia" → "ZrO2".
  Drop crystal-phase prefixes (γ, α, β) at the family level.

RULE 5 — Do NOT merge across these chemical distinctions:
  - bare support vs supported metal
  - different active metals / different number of metals
  - different supports
  - different reaction roles (control / blank / target) — but these roles themselves do NOT force separation; a target and a control of the same material can merge
  - biological catalyst vs chemical catalyst
  - carbon material types (activated carbon ≠ CNT ≠ biochar ≠ coke ≠ coal char)

RULE 6 — Conservative behavior.
  If unsure whether two families are the same material, KEEP THEM SEPARATE.
  Do NOT invent a new name that no input family used — the final canonical should be one of the input family names (the most informative / most standard one).

━━━ INPUT FORMAT ━━━
A JSON array of family records:
[{"family": "HZSM-5", "members_sample": ["HZSM-5", "nano-ZSM-5", ...], "count": 6}, ...]

━━━ OUTPUT FORMAT ━━━
Return ONLY a JSON array mapping each input family to its (possibly same) canonical family:
[{"family": "HZSM-5", "canonical": "HZSM-5"},
 {"family": "ZSM-5 zeolite", "canonical": "HZSM-5"},
 {"family": "zeolite", "canonical": "HZSM-5"},
 ...]

Every input family MUST appear exactly once in the output. No explanation, no markdown fence."""


def build_user_prompt(records: list[dict]) -> str:
    lines = [
        f"Deduplicate these {len(records)} catalyst family names. For each input family, return the canonical family it should merge into (can be itself).",
        "Each record shows the family name, a small sample of underlying catalyst names, and the total member count.\n",
        "INPUT:",
        json.dumps(records, ensure_ascii=False),
        "\nReturn a JSON array mapping every input family to its canonical family. Every family MUST appear exactly once."
    ]
    return "\n".join(lines)


def call_llm(records: list[dict], api_key: str) -> list[dict]:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 6000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(records)},
        ],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/chat/completions",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"].strip()

            if "```" in text:
                m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
                if m:
                    text = m.group(1).strip()

            mapping = json.loads(text)
            if not isinstance(mapping, list):
                raise ValueError("response is not a list")

            input_set = {r["family"] for r in records}
            validated = []
            seen = set()
            for m in mapping:
                fam = (m.get("family") or "").strip()
                canon = (m.get("canonical") or "").strip()
                if fam in input_set and canon and fam not in seen:
                    seen.add(fam)
                    validated.append({"family": fam, "canonical": canon})

            missing = input_set - seen
            if missing:
                print(f"  Warning: {len(missing)} families missing in LLM response; keeping them unchanged")
                for fam in missing:
                    validated.append({"family": fam, "canonical": fam})

            return validated
        except Exception as exc:
            print(f"  Attempt {attempt + 1} failed: {exc}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    print(f"  FATAL: all {MAX_RETRIES} attempts failed")
    return [{"family": r["family"], "canonical": r["family"]} for r in records]


def _resolve_transitive(mapping: dict) -> dict:
    """如果 A -> B -> C，把所有都折叠到最终的根（union-find 式）。"""
    def find(x, depth=0):
        if depth > 50:
            return x
        nxt = mapping.get(x, x)
        if nxt == x:
            return x
        return find(nxt, depth + 1)
    return {k: find(k) for k in mapping}


def main():
    if not API_KEY:
        raise SystemExit("Missing CATALYST_LLM_API_KEY / BLTCY_API_KEY.")

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        first_pass = json.load(f)
    print(f"Loaded {len(first_pass)} first-pass catalyst records from {INPUT_PATH}")

    # 聚合：按 canonical_catalyst_family 统计成员和数量
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
        records.append({
            "family": fam,
            "members_sample": uniq[:5],
            "count": len(members),
        })
    records.sort(key=lambda r: -r["count"])
    print(f"Unique families to dedup: {len(records)}")

    # 分批调用（通常单批就够了，但保留分批能力以防超长）
    results = []
    if len(records) <= BATCH_SIZE:
        print(f"Calling LLM with {len(records)} families in one batch...")
        results = call_llm(records, API_KEY)
    else:
        batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
        print(f"Calling LLM with {len(batches)} batches...")
        for i, batch in enumerate(batches, 1):
            print(f"  Batch {i}/{len(batches)} ({len(batch)} families)...")
            results.extend(call_llm(batch, API_KEY))
            if i < len(batches):
                time.sleep(1)

    # 构建映射并折叠传递链
    mapping = {r["family"]: r["canonical"] for r in results}
    mapping = _resolve_transitive(mapping)

    # 保存映射
    merged_count = sum(1 for k, v in mapping.items() if k != v)
    unique_after = len(set(mapping.values()))
    print(f"\n==== Dedup summary ====")
    print(f"  Input families:  {len(mapping)}")
    print(f"  Output families: {unique_after}")
    print(f"  Merged entries:  {merged_count}")
    print(f"  Compression:     {len(mapping)} -> {unique_after} ({len(mapping)/max(unique_after,1):.2f}x)")

    merges = [(k, v) for k, v in mapping.items() if k != v]
    if merges:
        print("\nSample merges:")
        for k, v in sorted(merges)[:15]:
            print(f"  {k!r:40s} -> {v!r}")

    with open(MAP_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"\nWrote mapping to {MAP_OUTPUT}")

    # 备份并更新 catalyst_family_result.json
    if not BACKUP_PATH.exists():
        shutil.copy(INPUT_PATH, BACKUP_PATH)
        print(f"Backup saved to {BACKUP_PATH}")

    updated = []
    for item in first_pass:
        new_item = dict(item)
        old_fam = (item.get("canonical_catalyst_family") or item.get("canonical_name") or "").strip()
        if old_fam and old_fam in mapping:
            new_fam = mapping[old_fam]
            new_item["canonical_catalyst_family"] = new_fam
            # 兼容旧字段
            new_item["canonical_name"] = new_fam
        updated.append(new_item)

    with open(INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    print(f"Updated {INPUT_PATH} with deduplicated families")


if __name__ == "__main__":
    main()
