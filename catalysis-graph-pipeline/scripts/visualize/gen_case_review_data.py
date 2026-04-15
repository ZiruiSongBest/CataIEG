"""Generate paper_bundles.json for case-review.html.

For each Paper, collects all instance nodes belonging to it plus connected
edges (and ontology edges that touch its instances). Outputs:
  <OUTPUT_DIR>/paper_bundles.json

For large graphs (150k papers), this file can be huge. Consider running it
per-shard and loading one bundle at a time in the UI.
"""
import json
import os
import sys
from pathlib import Path

OUTPUT_DIR = os.environ.get("GRAPH_OUTPUT_DIR", "graph_output")

NODES_FILE = Path(OUTPUT_DIR) / "nodes.jsonl"
EDGES_FILE = Path(OUTPUT_DIR) / "edges.jsonl"
OUT_FILE = Path(OUTPUT_DIR) / "paper_bundles.json"

INSTANCE_PREFIXES = (
    "reaction:", "catalyst:", "procedure:", "step:",
    "char:", "perf:", "op:", "metric:",
    "claim:", "evidence:",
)


def main():
    if not NODES_FILE.exists():
        sys.exit(f"Missing {NODES_FILE}. Run the graph builder first.")

    nodes = []
    with open(NODES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            nodes.append(json.loads(line))

    edges = []
    with open(EDGES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            edges.append(json.loads(line))

    papers = [n for n in nodes if n["node_type"] == "Paper"]
    papers.sort(key=lambda n: (n.get("year") or 0, n.get("doi", "")))

    # uid -> paper_uid
    uid_to_paper = {}
    for n in nodes:
        uid = n["uid"]
        parts = uid.split(":")
        if len(parts) >= 2 and any(uid.startswith(p) for p in INSTANCE_PREFIXES):
            uid_to_paper[uid] = f"paper:{parts[1]}"

    bundles = []
    for paper in papers:
        paper_uid = paper["uid"]
        bundle_nodes = [paper]
        for n in nodes:
            if n["uid"] != paper_uid and uid_to_paper.get(n["uid"]) == paper_uid:
                bundle_nodes.append(n)

        bundle_node_uids = {n["uid"] for n in bundle_nodes}
        bundle_edges = []
        for e in edges:
            src_in = e["source"] in bundle_node_uids
            tgt_in = e["target"] in bundle_node_uids
            if src_in and tgt_in:
                bundle_edges.append(e)
            elif src_in and e["target"].startswith("onto:"):
                bundle_edges.append(e)
            elif tgt_in and e["source"].startswith("onto:"):
                bundle_edges.append(e)

        bundles.append({"paper": paper, "nodes": bundle_nodes, "edges": bundle_edges})

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(bundles, f, ensure_ascii=False)

    print(f"Wrote {len(bundles)} paper bundles to {OUT_FILE}")


if __name__ == "__main__":
    main()
