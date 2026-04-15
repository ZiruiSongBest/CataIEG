# Scaling Guide: 150k Papers

## Rough cost estimates (per 100 papers, extrapolated)

Empirical numbers from the 100-paper reference run:
- Reactions: ~160 per 100 papers → **240k reactions** for 150k papers
- Catalysts: ~360 per 100 papers → **540k catalysts** for 150k papers
- MechanisticClaims: ~410 per 100 papers → **615k claims** for 150k papers
- Nodes: ~67 per paper → **10M nodes**, **45M edges** at 150k

## LLM call volume

With BATCH_SIZE=20:
- Reaction LLM calls: 240k / 20 = **12k batches**
- Catalyst LLM calls: 540k / 20 = **27k batches**
- Family dedup: depends on unique families (usually ~1k–3k unique → a few batches)

Assume 3s per call with max_tokens=4096. With LLM_CONCURRENCY=16:
- Reaction: 12k / 16 × 3s ≈ 38 min
- Catalyst: 27k / 16 × 3s ≈ 84 min
- **Total per-node LLM work ≈ 2 hours single-machine** (if the API isn't rate-limited)

## Recommended parameters

| Scale | shard-size | shard-workers | LLM_CONCURRENCY | Notes |
|---|---|---|---|---|
| < 1k | 1 shard | 1 | 8 | `run_pipeline.sh` is fine |
| 1k–10k | 1000 | 2 | 8 | `run_sharded.py` |
| 10k–50k | 1000 | 4 | 12 | watch API quota |
| 50k–150k | 1000–2000 | 4–8 | 16 | multi-machine, stagger start times |

The product `shard_workers × LLM_CONCURRENCY` is your effective concurrency
at the API. Don't exceed your provider's rate limit.

## Disk and memory

Per-shard output (1000 papers):
- `nodes.jsonl` ≈ 50–80 MB
- `edges.jsonl` ≈ 200–300 MB
- `paper_bundles.json` ≈ 60 MB

At 150 shards you get ~40 GB of raw graph data. Recommendations:
- Keep `paper_bundles.json` per-shard (don't merge). The Case Review UI can be
  pointed at individual shard files.
- Merged `nodes.jsonl` / `edges.jsonl` is worthwhile for cross-shard analysis
  (link prediction, global stats) but is 40+ GB. Use streaming tools (`jq`,
  Polars) rather than loading into Pandas.
- `edge_explorer_data.json` only contains aggregated co-occurrence edges, so
  it stays manageable (~50 MB) even for 150k papers.

## Two-stage strategy (recommended for 150k)

**Stage 1 — local shard graphs (parallel, recoverable):**
```bash
python3 scripts/run_sharded.py --input all.jsonl --outdir run01 --shard-size 1000 --shard-workers 6
```
Per-shard LLM normalization runs in isolation. If a shard fails, only that
shard needs to rerun. Local ReactionTemplates and CatalystFamilies are useful
on their own for per-shard analysis.

**Stage 2 — global family consolidation:**
After all shards finish, merge, then run one global dedup pass so that HZSM-5
from shard 001 is recognized as the same family as HZSM-5 in shard 150:

```bash
cd run01/graph_output
GRAPH_OUTPUT_DIR=$PWD python3 ../../scripts/build_graph/llm_dedup_catalyst_families.py
GRAPH_OUTPUT_DIR=$PWD python3 ../../scripts/build_graph/main.py
```

The dedup input at this stage is the *union* of all shards'
`canonical_catalyst_family` labels (a few thousand entries at most), so a
single big LLM batch (DEDUP_BATCH_SIZE=200+) is enough.

## Rate-limit resilience

The LLM client (`llm_client.py`) retries each call up to `LLM_MAX_RETRIES=3`
with exponential-ish backoff (`LLM_RETRY_DELAY × attempt`). For API providers
with strict rate limits:
- Cap `LLM_CONCURRENCY` at whatever your quota allows
- Keep `shard-workers × LLM_CONCURRENCY ≤ quota`
- Set `LLM_RETRY_DELAY=15` to back off harder

Each normalization script checkpoints to `_llm_progress_*.json` every 5
batches. Interrupt (Ctrl-C) is safe: rerun the same command and it resumes.

## Cost reduction ideas

1. **Smaller model for catalysts** — `claude-haiku-4-5-20251001` is ~5× cheaper
   and normalization is a structured NER-like task; for shards where precision
   matters less (exploratory runs), run haiku, then spot-check.
2. **Skip LLM on obviously-simple cases** — the fallback rule in
   `phase3b_cat_family.py` handles many supported-metal patterns; you can
   pre-filter candidates and only send ambiguous ones to LLM.
3. **Batch larger** — up to `BATCH_SIZE=40` still fits in 4096 tokens for short
   catalyst names; test token budget before cranking.
4. **Share family dedup across runs** — `catalyst_family_dedup_map.json` can be
   seeded from a previous run to warm-start.

## Common failure modes

- **JSON parse error from LLM**: usually means response was truncated
  (`LLM_MAX_TOKENS` too small). Bump to 6000 or drop `BATCH_SIZE`.
- **`ConnectionResetError`**: increase `LLM_TIMEOUT`, check API provider status.
- **Shard crashes midway**: look at `run01/_shard_outputs/<shard>/pipeline.log`.
  The `_llm_progress_catalyst.json` / `_llm_progress_reaction.json` inside that
  shard directory preserve partial progress; rerun the shard, it resumes.
- **Merged nodes.jsonl has duplicate UIDs across shards**: the merger dedups
  by UID, but edges referencing both variants may be kept. `main.py`'s post-
  processing removes dangling edges; run it on the merged graph if needed.
