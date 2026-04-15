"""Sharded pipeline runner for large-scale (e.g. 150k papers) processing.

Splits the input JSONL into fixed-size shards, runs the full pipeline on each
shard in parallel (process-level), then merges the per-shard outputs into one
consolidated graph.

Why shard?
  * LLM normalization runs per-shard so failures are recoverable at shard
    granularity, not for the whole 150k.
  * Peak memory stays bounded (each shard is ~1-2k papers).
  * You can run shards on multiple machines.

Usage:
  BLTCY_API_KEY=... LLM_CONCURRENCY=16 \
  python3 run_sharded.py \
    --input /path/to/all_papers.jsonl \
    --outdir /path/to/out \
    --shard-size 1000 \
    --shard-workers 4

  # To merge only (after all shards done):
  python3 run_sharded.py --outdir /path/to/out --merge-only
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BUILD_DIR = SCRIPT_DIR / "build_graph"
VIZ_DIR = SCRIPT_DIR / "visualize"
RUN_SH = SCRIPT_DIR / "run_pipeline.sh"


def split_jsonl(input_path: Path, shards_dir: Path, shard_size: int) -> list[Path]:
    shards_dir.mkdir(parents=True, exist_ok=True)
    shard_paths = []
    with open(input_path, "r", encoding="utf-8") as f:
        buf = []
        shard_idx = 0
        for line in f:
            buf.append(line)
            if len(buf) >= shard_size:
                p = shards_dir / f"shard_{shard_idx:05d}.jsonl"
                p.write_text("".join(buf), encoding="utf-8")
                shard_paths.append(p)
                buf = []
                shard_idx += 1
        if buf:
            p = shards_dir / f"shard_{shard_idx:05d}.jsonl"
            p.write_text("".join(buf), encoding="utf-8")
            shard_paths.append(p)
    return shard_paths


def run_one_shard(shard_input: Path, shard_output: Path, skip_rxn=False, skip_cat=False, skip_dedup=False):
    env = os.environ.copy()
    env["GRAPH_INPUT_FILE"] = str(shard_input)
    env["GRAPH_OUTPUT_DIR"] = str(shard_output)
    args = ["bash", str(RUN_SH)]
    if skip_rxn:
        args.append("--skip-llm-reactions")
    if skip_cat:
        args.append("--skip-llm-catalysts")
    if skip_dedup:
        args.append("--skip-dedup")
    print(f"[shard] starting {shard_input.name}")
    log_path = shard_output / "pipeline.log"
    shard_output.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    print(f"[shard] done    {shard_input.name}")
    return shard_output


def merge_jsonl(shard_dirs: list[Path], filename: str, out_path: Path):
    """Concatenate per-shard JSONL files. Deduplication by UID for nodes."""
    seen_uids = set()
    total = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for d in shard_dirs:
            p = d / filename
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if filename == "nodes.jsonl":
                        n = json.loads(line)
                        if n["uid"] in seen_uids:
                            continue
                        seen_uids.add(n["uid"])
                    out.write(line)
                    total += 1
    print(f"[merge] {filename}: {total} entries -> {out_path}")


def merge_llm_results(shard_dirs: list[Path], out_dir: Path):
    """Merge the per-shard catalyst/reaction LLM result JSONs for traceability."""
    for name in ("catalyst_family_result.json", "reaction_template_result.json",
                 "catalyst_family_dedup_map.json"):
        merged = []
        mapping = {}
        for d in shard_dirs:
            p = d / name
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                merged.extend(data)
            elif isinstance(data, dict):
                mapping.update(data)
        if merged:
            with open(out_dir / name, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            print(f"[merge] {name}: {len(merged)} records")
        elif mapping:
            with open(out_dir / name, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            print(f"[merge] {name}: {len(mapping)} mappings")


def merge_stats(shard_dirs: list[Path], out_path: Path):
    node_cnt = Counter()
    edge_cnt = Counter()
    total_nodes = total_edges = 0
    for d in shard_dirs:
        sp = d / "stats.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text(encoding="utf-8"))
        total_nodes += s.get("total_nodes", 0)
        total_edges += s.get("total_edges", 0)
        for k, v in (s.get("node_type_counts") or {}).items():
            node_cnt[k] += v
        for k, v in (s.get("edge_type_counts") or {}).items():
            edge_cnt[k] += v
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "node_type_counts": dict(node_cnt),
            "edge_type_counts": dict(edge_cnt),
            "shard_count": len(shard_dirs),
        }, f, ensure_ascii=False, indent=2)
    print(f"[merge] stats.json: {total_nodes} nodes, {total_edges} edges, {len(shard_dirs)} shards")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, help="Full JSONL (sample_6_task format)")
    ap.add_argument("--outdir", type=Path, required=True, help="Output root")
    ap.add_argument("--shard-size", type=int, default=1000)
    ap.add_argument("--shard-workers", type=int, default=2,
                    help="How many shards to run in parallel. Keep small: each shard already uses many LLM workers.")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--skip-llm-reactions", action="store_true")
    ap.add_argument("--skip-llm-catalysts", action="store_true")
    ap.add_argument("--skip-dedup", action="store_true")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    shards_dir = args.outdir / "_shards"
    shard_out_root = args.outdir / "_shard_outputs"

    if not args.merge_only:
        if not args.input:
            sys.exit("--input is required unless --merge-only")
        print(f"[shard] splitting {args.input} into shards of {args.shard_size}...")
        shard_paths = split_jsonl(args.input, shards_dir, args.shard_size)
        print(f"[shard] {len(shard_paths)} shards created")

        shard_out_root.mkdir(parents=True, exist_ok=True)
        shard_dirs = [shard_out_root / sp.stem for sp in shard_paths]

        with ProcessPoolExecutor(max_workers=args.shard_workers) as ex:
            futures = {
                ex.submit(run_one_shard, sp, sd,
                          args.skip_llm_reactions,
                          args.skip_llm_catalysts,
                          args.skip_dedup): (sp, sd)
                for sp, sd in zip(shard_paths, shard_dirs)
            }
            for fut in as_completed(futures):
                sp, sd = futures[fut]
                try:
                    fut.result()
                except Exception as exc:
                    print(f"[shard] FAILED {sp.name}: {exc}")

    # Merge
    shard_dirs = sorted([d for d in shard_out_root.iterdir() if d.is_dir()]) if shard_out_root.exists() else []
    if not shard_dirs:
        sys.exit(f"No shard outputs in {shard_out_root}")

    final_out = args.outdir / "graph_output"
    final_out.mkdir(exist_ok=True)
    print(f"\n[merge] merging {len(shard_dirs)} shards into {final_out}")

    merge_jsonl(shard_dirs, "nodes.jsonl", final_out / "nodes.jsonl")
    merge_jsonl(shard_dirs, "edges.jsonl", final_out / "edges.jsonl")
    merge_llm_results(shard_dirs, final_out)
    merge_stats(shard_dirs, final_out / "stats.json")

    print("\nDone. Note: per-shard graphs each compute their own ReactionTemplates, CatalystFamilies, and co-occurrence edges locally.")
    print("If you want global ReactionTemplate/CatalystFamily across all shards, run llm_dedup_catalyst_families.py and a rebuild on the merged input.")


if __name__ == "__main__":
    main()
