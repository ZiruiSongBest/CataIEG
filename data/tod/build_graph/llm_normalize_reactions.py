"""LLM 批量归一化反应名称 → canonical_reaction_name + canonical_reaction_aliases.

输出 graph_output/reaction_template_result.json 供 phase3a 消费。
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("REACTION_LLM_BASE_URL") or os.environ.get("CATALYST_LLM_BASE_URL", "https://api.bltcy.ai/v1")
API_KEY = (
    os.environ.get("REACTION_LLM_API_KEY")
    or os.environ.get("CATALYST_LLM_API_KEY")
    or os.environ.get("BLTCY_API_KEY")
)
MODEL = os.environ.get("REACTION_LLM_MODEL") or os.environ.get("CATALYST_LLM_MODEL", "claude-sonnet-4-6")
BATCH_SIZE = 20
MAX_RETRIES = 3
RETRY_DELAY = 5

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "graph_output" / "reaction_names_for_llm.json"
OUTPUT_PATH = BASE_DIR / "graph_output" / "reaction_template_result.json"
PROGRESS_PATH = BASE_DIR / "graph_output" / "_llm_progress_reaction.json"


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
* Use a lower-level specialized reaction name instead of a higher-level generic reaction name whenever possible (e.g., preferential CO oxidation, not CO oxidation).

B) Keep distinctions that matter chemically
Do NOT collapse across these differences:
* thermal reforming vs electrochemical reduction vs photocatalytic reduction vs plasma conversion
* hydrogenation vs hydrogenolysis vs dehydrogenation
* inverse direction of one reaction process (e.g., NH3 synthesis vs NH3 decomposition)
* half reaction or part of the reaction vs overall reaction (e.g., OER vs overall water splitting)
* CO oxidation vs VOC oxidation
* CO2 hydrogenation to methanol vs CO2RR
* pollutant degradation vs pollutant adsorption/removal
* desulfurization / denitrification / simultaneous desulfurization and denitrification should remain distinct unless the input clearly indicates a more standard single reaction name

C) Use broad common names only when appropriate
* If the entry clearly describes a named reaction subtype, use the subtype rather than a broad umbrella.
   * Example: use "glycerol steam reforming", not just "steam reforming"
   * use "NH3-SCR" if NH3 + NOx/SCR is clearly supported
* If the substrate-specific reaction is the common name used in the field, keep the substrate in the canonical name.
   * Examples: "glycerol steam reforming", "ethanol steam reforming", "methane dry reforming"

D) Environmental remediation cases
* Normalize to the most standard short reaction/process name supported by the entry.
* Examples: "SO2 removal", "flue gas desulfurization", "simultaneous SO2/NOx removal", "VOC oxidation", "CO oxidation", "pollutant photodegradation".
* Do NOT force an oxidation-family name if the actual entry is primarily removal/capture/remediation of SO2/NOx.

E) Product-specific and multi-product cases
* If one main target product is explicit and defines the common reaction name, use it (e.g., "CO2 hydrogenation to methanol").
* If the reaction is usually named by feedstock rather than product, use the feedstock-based name (e.g., "glycerol steam reforming").
* For multi-product electro/photo reactions, prefer the standard family name if supported (e.g., "CO2RR", "photocatalytic CO2 reduction").

F) Ambiguity handling
* If normalization is uncertain, choose the safest conservative normalized name or the original reported name.
* Do NOT invent abbreviations.

Return EXACTLY this JSON schema for each reaction:
{
"uid": "string",
"canonical_reaction_name": "string",
"canonical_reaction_aliases": ["string"]
}

Return ONLY a JSON array of such objects. No markdown, no explanation."""


def build_user_prompt(batch: list[dict]) -> str:
    lines = [
        f"Normalize these {len(batch)} reactions. For each, determine canonical_reaction_name and canonical_reaction_aliases following the system rules.\n",
        "Each entry is formatted as key=value pairs separated by ' | '.\n",
        "KEY FIELDS TO EXAMINE:",
        "- name: reaction_name_reported",
        "- domain: reaction_domain",
        "- class: reaction_class",
        "- family: reaction_family label(s)",
        "- transformation: a short description of the transformation",
        "- reactants: list of reactants",
        "- products: list of target products\n",
        "REACTIONS:\n",
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
    lines.append(f"\nReturn a JSON array of exactly {len(batch)} objects with uid, canonical_reaction_name, and canonical_reaction_aliases.")
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
                name = (r.get("canonical_reaction_name") or "").strip()
                aliases = r.get("canonical_reaction_aliases", [])
                if not isinstance(aliases, list):
                    aliases = []
                if not name:
                    continue
                validated.append({
                    "uid": uid,
                    "canonical_reaction_name": name,
                    "canonical_reaction_aliases": aliases,
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
            "Missing REACTION_LLM_API_KEY / CATALYST_LLM_API_KEY / BLTCY_API_KEY. "
            "Set one of them before running this script."
        )

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        reactions = json.load(f)
    print(f"Loaded {len(reactions)} reactions from {INPUT_PATH}")

    completed = {}
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            progress = json.load(f)
        for r in progress:
            completed[r["uid"]] = r
        print(f"Resuming: {len(completed)} already normalized")

    remaining = [item for item in reactions if item["uid"] not in completed]
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
            print(f"  Got {len(results)} results, total: {len(completed)}/{len(reactions)}")

            if batch_index < len(batches):
                time.sleep(1)

    all_results = []
    for rxn in reactions:
        r = completed.get(rxn["uid"])
        if r:
            all_results.append(r)
        else:
            all_results.append({
                "uid": rxn["uid"],
                "canonical_reaction_name": "",
                "canonical_reaction_aliases": [],
            })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nDone! Wrote {len(all_results)} results to {OUTPUT_PATH}")

    names = [r["canonical_reaction_name"] for r in all_results if r.get("canonical_reaction_name")]
    print(f"  Unique canonical_reaction_name: {len(set(names))} (from {len(names)})")
    print(f"  Compression: {len(names)}/{max(len(set(names)),1)} = {len(names)/max(len(set(names)),1):.1f}x")

    if PROGRESS_PATH.exists():
        try:
            PROGRESS_PATH.unlink()
        except PermissionError:
            pass


if __name__ == "__main__":
    main()
