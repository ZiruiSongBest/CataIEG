"""LLM 批量归一化催化剂名称 → canonical_catalyst_name + canonical_catalyst_family + canonical_aliases.

Paths controlled by config.py (CAT_NAMES_FOR_LLM, CAT_FAMILY_RESULT).
Parallel execution via llm_client.run_batches_parallel.
Checkpointing: saves progress every N batches in case of interruption.
"""
import json
import os
import threading
from pathlib import Path

from config import CAT_NAMES_FOR_LLM, CAT_FAMILY_RESULT, OUTPUT_DIR
from llm_client import call_chat, parse_json_array, run_batches_parallel

BATCH_SIZE = int(os.environ.get("CATALYST_BATCH_SIZE", "20"))
PROGRESS_PATH = Path(OUTPUT_DIR) / "_llm_progress_catalyst.json"


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
{"uid": "string", "canonical_catalyst_name": "string", "canonical_catalyst_family": "string", "canonical_aliases": ["string"]}

Return ONLY a JSON array of such objects. No markdown, no explanation."""


def build_user_prompt(batch):
    lines = [
        f"Normalize these {len(batch)} catalysts. For each, determine canonical_catalyst_name, canonical_catalyst_family, and canonical_aliases following the system rules.\n",
        "Each entry is formatted as key=value pairs separated by ' | '.\n",
        "CATALYSTS:",
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
    lines.append(f"\nReturn a JSON array of exactly {len(batch)} objects.")
    return "\n".join(lines)


def process_batch(batch):
    try:
        text = call_chat(SYSTEM_PROMPT, build_user_prompt(batch))
        raw = parse_json_array(text)
    except Exception as exc:
        print(f"  [catalyst batch {len(batch)} items] failed: {exc}")
        return []
    uid_set = {item["uid"] for item in batch}
    out = []
    for r in raw:
        uid = r.get("uid")
        if uid not in uid_set:
            continue
        name = (r.get("canonical_catalyst_name") or "").strip()
        family = (r.get("canonical_catalyst_family") or "").strip() or name
        aliases = r.get("canonical_aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        if not name:
            continue
        out.append({
            "uid": uid,
            "canonical_catalyst_name": name,
            "canonical_catalyst_family": family,
            "canonical_aliases": aliases,
            "canonical_name": family,  # legacy compat
        })
    return out


_progress_lock = threading.Lock()


def main():
    with open(CAT_NAMES_FOR_LLM, "r", encoding="utf-8") as f:
        catalysts = json.load(f)
    print(f"[catalyst] loaded {len(catalysts)} catalysts")

    completed = {}
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            for r in json.load(f):
                completed[r["uid"]] = r
        print(f"[catalyst] resuming with {len(completed)} already done")

    remaining = [c for c in catalysts if c["uid"] not in completed]
    if remaining:
        batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
        print(f"[catalyst] {len(batches)} batches of ~{BATCH_SIZE}, concurrency={os.environ.get('LLM_CONCURRENCY','8')}")

        def on_progress(done, total, batch_results):
            with _progress_lock:
                for r in batch_results:
                    completed[r["uid"]] = r
                if done % 5 == 0 or done == total:
                    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                        json.dump(list(completed.values()), f, ensure_ascii=False)
                    print(f"  [catalyst] {done}/{total} batches, {len(completed)} items normalized")

        run_batches_parallel(batches, process_batch, progress_callback=on_progress)

    # Final write
    all_results = []
    for c in catalysts:
        r = completed.get(c["uid"])
        if r:
            all_results.append(r)
        else:
            all_results.append({
                "uid": c["uid"], "canonical_catalyst_name": "",
                "canonical_catalyst_family": "", "canonical_aliases": [], "canonical_name": "",
            })

    with open(CAT_FAMILY_RESULT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    families = {r["canonical_catalyst_family"] for r in all_results if r.get("canonical_catalyst_family")}
    names = {r["canonical_catalyst_name"] for r in all_results if r.get("canonical_catalyst_name")}
    print(f"[catalyst] done: {len(all_results)} records -> {len(names)} unique names, {len(families)} unique families")

    if PROGRESS_PATH.exists():
        try:
            PROGRESS_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
