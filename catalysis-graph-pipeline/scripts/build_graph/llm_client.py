"""Shared LLM client with parallel execution and retry.

Environment variables:
  BLTCY_API_KEY (or CATALYST_LLM_API_KEY / REACTION_LLM_API_KEY) — API key
  LLM_BASE_URL (or CATALYST_LLM_BASE_URL) — API base (default: https://api.bltcy.ai/v1)
  LLM_MODEL (or CATALYST_LLM_MODEL) — model name (default: claude-sonnet-4-6)
  LLM_CONCURRENCY — concurrent request workers (default: 8)
  LLM_MAX_TOKENS — max_tokens per call (default: 4096)
"""
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def get_config():
    return {
        "base_url": os.environ.get("LLM_BASE_URL") or os.environ.get("CATALYST_LLM_BASE_URL", "https://api.bltcy.ai/v1"),
        "api_key": (
            os.environ.get("BLTCY_API_KEY")
            or os.environ.get("CATALYST_LLM_API_KEY")
            or os.environ.get("REACTION_LLM_API_KEY")
        ),
        "model": os.environ.get("LLM_MODEL") or os.environ.get("CATALYST_LLM_MODEL", "claude-sonnet-4-6"),
        "concurrency": int(os.environ.get("LLM_CONCURRENCY", "8")),
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "4096")),
        "timeout": int(os.environ.get("LLM_TIMEOUT", "180")),
        "max_retries": int(os.environ.get("LLM_MAX_RETRIES", "3")),
        "retry_delay": int(os.environ.get("LLM_RETRY_DELAY", "5")),
    }


def _strip_code_fence(text: str) -> str:
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text.strip()


def call_chat(system_prompt: str, user_prompt: str, cfg: dict | None = None) -> str:
    """Single chat completion call. Returns the raw text (caller parses JSON)."""
    cfg = cfg or get_config()
    if not cfg["api_key"]:
        raise RuntimeError("Missing BLTCY_API_KEY / CATALYST_LLM_API_KEY / REACTION_LLM_API_KEY")

    payload = json.dumps({
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    last_exc = None
    for attempt in range(cfg["max_retries"]):
        try:
            req = urllib.request.Request(
                f"{cfg['base_url']}/chat/completions",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            last_exc = exc
            if attempt < cfg["max_retries"] - 1:
                time.sleep(cfg["retry_delay"] * (attempt + 1))

    raise RuntimeError(f"LLM call failed after {cfg['max_retries']} attempts: {last_exc}")


def parse_json_array(text: str) -> list:
    text = _strip_code_fence(text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("LLM response is not a JSON array")
    return data


def run_batches_parallel(
    batches: list,
    worker_fn,
    progress_callback=None,
    concurrency: int | None = None,
):
    """Run a list of batches through worker_fn with a thread pool.

    worker_fn(batch) -> list[result].
    Returns flat list of all results, preserving batch order.
    progress_callback(done, total, results_this_batch) is called per completed batch.
    """
    cfg = get_config()
    conc = concurrency or cfg["concurrency"]

    # Preserve order: index each batch
    indexed = list(enumerate(batches))
    out = [None] * len(batches)
    completed = 0

    with ThreadPoolExecutor(max_workers=conc) as ex:
        future_to_idx = {ex.submit(worker_fn, b): i for i, b in indexed}
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                out[idx] = fut.result() or []
            except Exception as exc:
                print(f"  [batch {idx}] FAILED: {exc}")
                out[idx] = []
            completed += 1
            if progress_callback:
                progress_callback(completed, len(batches), out[idx])

    flat = []
    for r in out:
        flat.extend(r)
    return flat
