"""LLM 批量归一化反应名称 → canonical_reaction_name + canonical_reaction_aliases.

Parallel batching via llm_client.
"""
import json
import os
import threading
from pathlib import Path

from config import RXN_NAMES_FOR_LLM, RXN_TEMPLATE_RESULT, OUTPUT_DIR
from llm_client import call_chat, parse_json_array, run_batches_parallel

BATCH_SIZE = int(os.environ.get("REACTION_BATCH_SIZE", "20"))
PROGRESS_PATH = Path(OUTPUT_DIR) / "_llm_progress_reaction.json"


SYSTEM_PROMPT = """You are a reaction normalization engine for heterogeneous catalysis data.

General rules
* Output ONLY valid JSON that matches the exact schema below. No markdown, no explanations, no extra keys.
* If a field is not supported by the input, omit it. Do NOT output null.
* Your job is to normalize different expressions of the SAME reaction into one short, common, stable, professional canonical name. Output the other commonly used names as reaction_aliases.
* Prefer the most widely used short community name when it is explicitly supported by the input fields.
* Do NOT over-specify conditions, catalysts, reactor types, supports, substrates, performance context, or mechanistic details in the canonical name.
* Do NOT merge genuinely different reactions into the same canonical name.
* If the input is too vague to safely normalize to a standard reaction name, keep the reported name.

Task
Given one reaction entry, produce:

1. canonical_reaction_name
* Keep it lowercase except standard abbreviations/formulas (e.g., OER, ORR, CO2RR, NH3 synthesis, glycerol steam reforming, CO oxidation, VOC oxidation, NH3 decomposition, methanol synthesis, F-T synthesis).
* Do not use broad names like methanation or oxidation.
* Prefer a standard reaction family name if clearly supported by:
   * reaction_family
   * or reaction_name_reported
   * or transformation
* If a family label in the input is clearly wrong or inconsistent with the reaction_name_reported/transformation/reactants/target_products, normalize based on the chemically consistent information and ignore the inconsistent family label.

2. canonical_reaction_aliases
* A short list of equivalent expressions explicitly supported by the input entry.
* Include only useful normalized aliases, not every wording variant.

Normalization rules
A) Priority for naming
* Highest priority: a clear standard reaction family/community name specific to the reaction and explicitly supported by the entry.
* If no clear family/community name is available, normalize from the chemically specific transformation and reactants/products.
* If both are vague, use a conservative cleaned version of reaction_name_reported.
* Use a lower-level specialized reaction name instead of a higher-level generic reaction name whenever possible.

B) Keep distinctions that matter chemically
Do NOT collapse across these differences:
* thermal reforming vs electrochemical reduction vs photocatalytic reduction vs plasma conversion
* hydrogenation vs hydrogenolysis vs dehydrogenation
* NH3 synthesis vs NH3 decomposition
* OER vs overall water splitting
* CO oxidation vs VOC oxidation
* CO2 hydrogenation to methanol vs CO2RR
* pollutant degradation vs pollutant adsorption/removal
* desulfurization / denitrification / simultaneous desulfurization and denitrification stay distinct

C) Use broad common names only when appropriate
* If the entry clearly describes a named reaction subtype, use the subtype rather than a broad umbrella.
* If the substrate-specific reaction is the common name used in the field, keep the substrate in the canonical name (e.g., "glycerol steam reforming", "ethanol steam reforming", "methane dry reforming").

D) Environmental remediation cases
* Normalize to the most standard short reaction/process name supported by the entry.
* Do NOT force an oxidation-family name if the actual entry is primarily removal/capture/remediation of SO2/NOx.

E) Product-specific and multi-product cases
* If one main target product is explicit, use it (e.g., "CO2 hydrogenation to methanol").
* If the reaction is usually named by feedstock, use the feedstock-based name.
* For multi-product electro/photo reactions, prefer the standard family name (e.g., "CO2RR").

F) Ambiguity handling
* If normalization is uncertain, choose the safest conservative normalized name or the original reported name.
* Do NOT invent abbreviations.

Return EXACTLY this JSON schema for each reaction:
{"uid": "string", "canonical_reaction_name": "string", "canonical_reaction_aliases": ["string"]}

Return ONLY a JSON array of such objects. No markdown, no explanation."""


def build_user_prompt(batch):
    lines = [
        f"Normalize these {len(batch)} reactions.\n",
        "Each entry is formatted as key=value pairs separated by ' | '.\n",
        "REACTIONS:",
    ]
    for item in batch:
        parts = [
            f"uid={item['uid']}",
            f"name={item.get('reaction_name_reported','')}",
            f"domain={item.get('reaction_domain','')}",
            f"class={item.get('reaction_class','')}",
            f"family=[{', '.join(item.get('reaction_family', []))}]",
        ]
        if item.get("transformation"):
            parts.append(f"transformation={item['transformation']}")
        if item.get("reactants"):
            parts.append(f"reactants=[{', '.join(item['reactants'])}]")
        if item.get("target_products"):
            parts.append(f"products=[{', '.join(item['target_products'])}]")
        lines.append(" | ".join(parts))
    lines.append(f"\nReturn a JSON array of exactly {len(batch)} objects.")
    return "\n".join(lines)


def process_batch(batch):
    try:
        text = call_chat(SYSTEM_PROMPT, build_user_prompt(batch))
        raw = parse_json_array(text)
    except Exception as exc:
        print(f"  [reaction batch {len(batch)} items] failed: {exc}")
        return []
    uid_set = {item["uid"] for item in batch}
    out = []
    for r in raw:
        uid = r.get("uid")
        if uid not in uid_set:
            continue
        name = (r.get("canonical_reaction_name") or "").strip()
        aliases = r.get("canonical_reaction_aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        if not name:
            continue
        out.append({
            "uid": uid,
            "canonical_reaction_name": name,
            "canonical_reaction_aliases": aliases,
        })
    return out


_progress_lock = threading.Lock()


def main():
    with open(RXN_NAMES_FOR_LLM, "r", encoding="utf-8") as f:
        reactions = json.load(f)
    print(f"[reaction] loaded {len(reactions)} reactions")

    completed = {}
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            for r in json.load(f):
                completed[r["uid"]] = r
        print(f"[reaction] resuming with {len(completed)} already done")

    remaining = [c for c in reactions if c["uid"] not in completed]
    if remaining:
        batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
        print(f"[reaction] {len(batches)} batches of ~{BATCH_SIZE}, concurrency={os.environ.get('LLM_CONCURRENCY','8')}")

        def on_progress(done, total, batch_results):
            with _progress_lock:
                for r in batch_results:
                    completed[r["uid"]] = r
                if done % 5 == 0 or done == total:
                    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                        json.dump(list(completed.values()), f, ensure_ascii=False)
                    print(f"  [reaction] {done}/{total} batches, {len(completed)} items normalized")

        run_batches_parallel(batches, process_batch, progress_callback=on_progress)

    all_results = []
    for r in reactions:
        done = completed.get(r["uid"])
        if done:
            all_results.append(done)
        else:
            all_results.append({
                "uid": r["uid"], "canonical_reaction_name": "", "canonical_reaction_aliases": [],
            })

    with open(RXN_TEMPLATE_RESULT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    names = {r["canonical_reaction_name"] for r in all_results if r.get("canonical_reaction_name")}
    print(f"[reaction] done: {len(all_results)} records -> {len(names)} unique canonical names")

    if PROGRESS_PATH.exists():
        try:
            PROGRESS_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
