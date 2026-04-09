"""LLM 批量归一化催化剂名称 → canonical_name.

输出 graph_output/catalyst_family_result.json 供 phase3b 消费。
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("CATALYST_LLM_BASE_URL", "https://api.bltcy.ai/v1")
API_KEY = os.environ.get("CATALYST_LLM_API_KEY") or os.environ.get("BLTCY_API_KEY")
MODEL = os.environ.get("CATALYST_LLM_MODEL", "claude-sonnet-4-6")
BATCH_SIZE = 40
MAX_RETRIES = 3
RETRY_DELAY = 5

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "graph_output" / "catalyst_names_for_llm.json"
OUTPUT_PATH = BASE_DIR / "graph_output" / "catalyst_family_result.json"
PROGRESS_PATH = BASE_DIR / "graph_output" / "_llm_progress.json"


SYSTEM_PROMPT = """You are a senior heterogeneous catalysis researcher performing catalyst identity resolution for a knowledge graph. Your task: assign each catalyst a canonical_name so that catalysts representing the SAME material entity across different papers are grouped together, while chemically distinct materials stay separate.

━━━ DECISION FRAMEWORK (apply in order) ━━━

STEP 1 — Determine the material identity class:
  a) Supported metal catalyst (active metal on a distinct support): canonical = "ActiveMetal/Support"
  b) Bulk / unsupported oxide or mixed oxide: canonical = formula, e.g. "Fe2O3", "CuZnAl-oxide"
  c) Zeolite or molecular sieve: canonical = framework code, e.g. "HZSM-5", "USY", "HY"
  d) Carbon material (char, coke, biochar, AC, CNT, graphene…): canonical = specific carbon type
  e) Biological catalyst: canonical = genus + species (keep organisms separate)
  f) No catalyst / blank / uncatalyzed: canonical = "no_catalyst"

STEP 2 — Apply these critical chemistry rules:

  RULE A — Supported metal ≠ bare support.
    "Ni/Al2O3" and "Al2O3" are DIFFERENT families. A supported metal catalyst and its bare support must NEVER share the same canonical_name, even if one is a control.

  RULE B — Supported metal ≠ bulk mixed oxide.
    "Ni/Al2O3" (Ni nanoparticles deposited on Al2O3 support) ≠ "NiAl-oxide" (co-precipitated or sol-gel NiAlOx mixed oxide). Check the platform label: "supported_metal_nanoparticles" → supported; "metal_oxides_hydroxides_oxyhydroxides" with no clear support → bulk oxide.

  RULE C — Active metal composition defines identity.
    "NiMo/Al2O3" ≠ "Ni/Al2O3" ≠ "Mo/Al2O3". Different active metal sets = different family. Order multi-metal alphabetically: "CoMo" not "MoCo". "NiMo" and "MoNi" are the SAME.

  RULE D — Support architecture matters when explicitly stated.
    "Ni/Al2O3" ≠ "Ni/Al2O3-coated cordierite" ≠ "Ni/Al2O3/Ni-foam". Keep these distinctions.

  RULE E — Role field is informational, NOT a grouping criterion.
    Two catalysts with role=target and role=control can still be the SAME family if they are the same material. But do NOT merge a target catalyst with its bare support just because both appear in the same paper.

  RULE F — Opaque codes need resolution.
    If a catalyst has a non-descriptive name (e.g. "G-91", "Catalyst A", "HT400"), look at ALL available fields (aliases, support, platform labels, series_name) to determine its actual identity. If you cannot determine what it is, use the opaque name as-is rather than guessing.

  RULE G — Loading and morphology are stripped.
    "5 wt% Ni/Al2O3" → "Ni/Al2O3". "Ni nanorods/Al2O3" → "Ni/Al2O3" (unless morphology defines a fundamentally different material class).

  RULE H — Zeolite series variants.
    Different Si/Al ratios, dealumination degrees, or post-treatments of the same framework type → SAME family. "HZSM-5(Si/Al=25)" and "HZSM-5(Si/Al=50)" → both "HZSM-5".

  RULE I — Carbon materials stay specific.
    Never merge: activated carbon, CNT, graphene, biochar, coal char, oil shale char, coke, fly-ash carbon. Preserve precursor distinctions. "Ni/activated carbon" ≠ "Ni/CNT" ≠ "Ni/biochar".

  RULE J — Normalize support names.
    γ-Al2O3, α-Al2O3, pseudo-boehmite → "Al2O3". silica → "SiO2". titania → "TiO2". ceria → "CeO2". zirconia → "ZrO2". "ordered mesoporous alumina" → "Al2O3".

STEP 3 — Cross-check:
  Before finalizing, verify: "Would a catalysis researcher reading two different papers recognize these as the same catalyst?" If no → separate families.

━━━ OUTPUT FORMAT ━━━
Return ONLY a JSON array: [{"uid": "...", "canonical_name": "..."}, ...]
No explanation, no markdown fence, just the raw JSON array."""


def build_user_prompt(batch: list[dict]) -> str:
    lines = [
        f"Normalize these {len(batch)} catalysts. For each, determine the canonical_name following the system rules.\n",
        "Each entry is formatted as key=value pairs separated by ' | '.\n",
        "KEY FIELDS TO EXAMINE:",
        "- name: the reported catalyst name from the paper",
        "- support: the substrate or support material (if any)",
        "- platform: material_platform label(s) — critical for distinguishing supported metals vs bulk oxides vs carbon etc.",
        "- site: active site form label(s)",
        "- role: target/control/baseline/blank_substrate — informational only, do NOT group by role",
        "- aliases: alternative names mentioned in the paper",
        "- series: series name if part of a systematic study",
        "- variant: what was varied in the series (e.g., loading, temperature)\n",
        "CATALYSTS:\n",
    ]
    for item in batch:
        parts = [f"uid={item['uid']}", f"name={item['name_reported']}"]
        if item.get("aliases"):
            parts.append(f"aliases=[{', '.join(item['aliases'])}]")
        parts.append(f"role={item.get('role', '')}")
        if item.get("series_name"):
            parts.append(f"series={item['series_name']}")
        if item.get("variant_rule") or item.get("variant_value"):
            parts.append(
                f"variant={item.get('variant_rule', '')}={item.get('variant_value', '')}".strip()
            )
        parts.append(f"support={item.get('substrate_or_support', '')}")
        parts.append(f"platform=[{', '.join(item.get('labels_material_platform', []))}]")
        if item.get("labels_active_site_form"):
            parts.append(f"site=[{', '.join(item['labels_active_site_form'])}]")
        lines.append(" | ".join(parts))
    lines.append(f"\nReturn a JSON array of exactly {len(batch)} objects with uid and canonical_name.")
    return "\n".join(lines)


def call_llm(batch: list[dict], api_key: str) -> list[dict]:
    user_msg = build_user_prompt(batch)

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
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
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"].strip()

            if "```" in text:
                match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
                if match:
                    text = match.group(1).strip()

            results = json.loads(text)
            if not isinstance(results, list):
                raise ValueError("Response is not a list")

            uid_set = {item["uid"] for item in batch}
            validated = []
            for result_item in results:
                if result_item.get("uid") in uid_set and result_item.get("canonical_name"):
                    validated.append({
                        "uid": result_item["uid"],
                        "canonical_name": result_item["canonical_name"],
                    })
            return validated
        except Exception as exc:
            print(f"  Attempt {attempt + 1} failed: {exc}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    print(f"  FATAL: all {MAX_RETRIES} attempts failed for batch")
    return []


def main():
    if not API_KEY:
        raise SystemExit(
            "Missing CATALYST_LLM_API_KEY or BLTCY_API_KEY. "
            "Set one of them before running this script."
        )

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        catalysts = json.load(f)
    print(f"Loaded {len(catalysts)} catalysts from {INPUT_PATH}")

    completed = {}
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            progress = json.load(f)
        for result_item in progress:
            completed[result_item["uid"]] = result_item["canonical_name"]
        print(f"Resuming: {len(completed)} already normalized")

    remaining = [item for item in catalysts if item["uid"] not in completed]
    print(f"Remaining: {len(remaining)} to normalize")

    if remaining:
        batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
        print(f"Processing {len(batches)} batches of ~{BATCH_SIZE}...")

        for batch_index, batch in enumerate(batches, 1):
            print(f"\nBatch {batch_index}/{len(batches)} ({len(batch)} items)...")
            results = call_llm(batch, API_KEY)
            for result_item in results:
                completed[result_item["uid"]] = result_item["canonical_name"]

            progress_data = [
                {"uid": uid, "canonical_name": canonical_name}
                for uid, canonical_name in completed.items()
            ]
            with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
            print(f"  Got {len(results)} results, total: {len(completed)}/{len(catalysts)}")

            if batch_index < len(batches):
                time.sleep(1)

    all_results = []
    for catalyst in catalysts:
        all_results.append({
            "uid": catalyst["uid"],
            "canonical_name": completed.get(catalyst["uid"], ""),
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nDone! Wrote {len(all_results)} results to {OUTPUT_PATH}")

    names = [item["canonical_name"] for item in all_results if item["canonical_name"]]
    unique = set(names)
    print(f"  Unique canonical names: {len(unique)} (from {len(names)} catalysts)")
    print(f"  Compression ratio: {len(names)}/{len(unique)} = {len(names) / max(len(unique), 1):.1f}x")

    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()


if __name__ == "__main__":
    main()
