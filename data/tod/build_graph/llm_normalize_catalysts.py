"""LLM 批量归一化催化剂名称 → canonical_catalyst_name + canonical_catalyst_family + canonical_aliases.

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
BATCH_SIZE = 20
MAX_RETRIES = 3
RETRY_DELAY = 5

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "graph_output" / "catalyst_names_for_llm.json"
OUTPUT_PATH = BASE_DIR / "graph_output" / "catalyst_family_result.json"
PROGRESS_PATH = BASE_DIR / "graph_output" / "_llm_progress_catalyst.json"


SYSTEM_PROMPT = """You are a catalyst normalization engine for heterogeneous catalysis data.

General rules
* Output ONLY valid JSON that matches the exact schema below. No markdown, no explanations, no extra keys.
* If a field is not supported by the input, omit it. Do NOT output null.
* Your job is to normalize different expressions of the same catalyst/material into one short, common, chemically meaningful canonical name.

Task
Given one catalyst entry, produce:

1. canonical_catalyst_name
* A short, simple, chemically meaningful normalized name for this specific catalyst record.
* Prefer standard catalyst notation or the clearest chemical/material name explicitly supported by the input.
* Keep essential identity information that distinguishes this catalyst from a materially different one.
* Remove non-essential wording such as "catalyst", "material", "sample", "commercial", "based", "combined", unless needed for meaning.
* Do NOT include vendor names, company names, catalog numbers, performance context, or long descriptive phrases.

2. canonical_catalyst_family
* A broader but still chemically meaningful family name for this catalyst.
* Describe secondary differences that do not change catalyst family identity but cause unnecessary fragmentation, such as crystal phase, loading, particle size, generic morphology, macroscopic form factor, shaping mode, generic processing parameters, and numerical series variables.
* Do not remove differences in the active component(s), the number of components, and the type of active-phase system.
* It may be the same as canonical_catalyst_name if no broader safe grouping is supported.
* Use a family name only when the input clearly supports one.

3. canonical_aliases
* Optional.
* A short list of useful alternative normalized names explicitly supported by the record.
* Include only meaningful aliases, not trivial wording variants.

Normalization rules
A) Preserve catalyst identity
Do NOT remove information that changes the catalyst into a different material, including when explicitly stated:
* active component identity
* promoter/dopant identity
* support/substrate identity when it is part of the catalyst identity
* explicit composition/loading if it is clearly part of the sample identity
* explicit series variant if it defines the material
* pretreatment-defined state if the record itself represents that distinct sample

B) Support/substrate handling
* If the active phase is clearly supported on or combined with a support/substrate that defines catalyst identity, include it in the canonical name.
* If the record is a bare support / blank substrate / no-catalyst control, normalize conservatively to the explicit material or blank identity stated in the record.

C) Conservative behavior
* If the record is too vague to safely compress into a more standard name, keep a conservative normalized name close to name_reported.
* Do NOT invent formulas, oxidation states, loadings, support relationships, or family names not explicitly supported.

D) Prefer chemical formulas or standard material expressions (e.g., ceria -> CeO2, titania -> TiO2, and montmorillonite modified with vanadium -> V-modified montmorillonite)

E) Handle @, /, -, on, and over contextually. When the input indicates that an active component is supported on a support, normalize it as X/Support (Pt on Al2O3 -> Pt/Al2O3). Sometimes they indicate a composite structure, core-shell, coverage, a modification relationship, or a sample code, retain the original form (TiO2-SiO2 retain as TiO2-SiO2 when it denotes a composite/mixed system; convert to TiO2/SiO2 only when a supported relationship is explicit)

F) Do not remove crystal phase, morphology, or similar descriptors that may affect identity (e.g., gamma-Al2O3 != Al2O3, Pt nanorods/Al2O3 != Pt/Al2O3)

G) If the original name does not explicitly specify support geometry, oxidation state, or exact chemical species, do not rewrite it into a more specific expression.
e.g.:
* V-modified montmorillonite != V/montmorillonite
* V-modified montmorillonite != VOx/montmorillonite
* cerium-modified alumina != CeO2/Al2O3

H) If a name explicitly states "with an X% loading":
* catalyst with a 0.5% Rh loading on GDC -> 0.5% Rh/GDC
If the name also contains explicit structural features that are used to distinguish sample identity, they may be retained:
* freeze-cast 0.5% Rh/GDC membrane catalyst

Return EXACTLY this JSON schema for each catalyst:
{
"uid": "string",
"canonical_catalyst_name": "string",
"canonical_catalyst_family": "string",
"canonical_aliases": ["string"]
}

Return ONLY a JSON array of such objects. No markdown, no explanation."""


def build_user_prompt(batch: list[dict]) -> str:
    lines = [
        f"Normalize these {len(batch)} catalysts. For each, determine canonical_catalyst_name, canonical_catalyst_family, and canonical_aliases following the system rules.\n",
        "Each entry is formatted as key=value pairs separated by ' | '.\n",
        "KEY FIELDS TO EXAMINE:",
        "- name: the reported catalyst name from the paper",
        "- support: the substrate or support material (if any)",
        "- platform: material_platform label(s)",
        "- site: active site form label(s)",
        "- role: target/control/baseline/blank_substrate",
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
    lines.append(f"\nReturn a JSON array of exactly {len(batch)} objects with uid, canonical_catalyst_name, canonical_catalyst_family, and canonical_aliases.")
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
            with urllib.request.urlopen(req, timeout=180) as resp:
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
            for r in results:
                uid = r.get("uid")
                if uid not in uid_set:
                    continue
                name = r.get("canonical_catalyst_name", "").strip()
                family = r.get("canonical_catalyst_family", "").strip() or name
                aliases = r.get("canonical_aliases", [])
                if not isinstance(aliases, list):
                    aliases = []
                if not name:
                    continue
                validated.append({
                    "uid": uid,
                    "canonical_catalyst_name": name,
                    "canonical_catalyst_family": family,
                    "canonical_aliases": aliases,
                    # 兼容旧字段名（phase3b 早期代码会读 canonical_name）
                    "canonical_name": family,
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
        for r in progress:
            completed[r["uid"]] = r
        print(f"Resuming: {len(completed)} already normalized")

    remaining = [item for item in catalysts if item["uid"] not in completed]
    print(f"Remaining: {len(remaining)} to normalize")

    if remaining:
        batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
        print(f"Processing {len(batches)} batches of ~{BATCH_SIZE}...")

        for batch_index, batch in enumerate(batches, 1):
            print(f"\nBatch {batch_index}/{len(batches)} ({len(batch)} items)...")
            results = call_llm(batch, API_KEY)
            for r in results:
                completed[r["uid"]] = r

            progress_data = list(completed.values())
            with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
            print(f"  Got {len(results)} results, total: {len(completed)}/{len(catalysts)}")

            if batch_index < len(batches):
                time.sleep(1)

    all_results = []
    for catalyst in catalysts:
        r = completed.get(catalyst["uid"])
        if r:
            all_results.append(r)
        else:
            all_results.append({
                "uid": catalyst["uid"],
                "canonical_catalyst_name": "",
                "canonical_catalyst_family": "",
                "canonical_aliases": [],
                "canonical_name": "",
            })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nDone! Wrote {len(all_results)} results to {OUTPUT_PATH}")

    families = [r["canonical_catalyst_family"] for r in all_results if r.get("canonical_catalyst_family")]
    names = [r["canonical_catalyst_name"] for r in all_results if r.get("canonical_catalyst_name")]
    print(f"  Unique canonical_catalyst_name: {len(set(names))} (from {len(names)})")
    print(f"  Unique canonical_catalyst_family: {len(set(families))} (from {len(families)})")
    print(f"  Family compression: {len(names)}/{max(len(set(families)),1)} = {len(names)/max(len(set(families)),1):.1f}x")

    if PROGRESS_PATH.exists():
        try:
            PROGRESS_PATH.unlink()
        except PermissionError:
            pass


if __name__ == "__main__":
    main()
