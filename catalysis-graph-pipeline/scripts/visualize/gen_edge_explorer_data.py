"""Generate edge_explorer_data.json for edge-explorer.html.

Groups edges by the 6 task categories + cross-paper bridging, and assembles
the co-occurrence edge list for interactive inspection.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

OUTPUT_DIR = os.environ.get("GRAPH_OUTPUT_DIR", "graph_output")
NODES_FILE = Path(OUTPUT_DIR) / "nodes.jsonl"
EDGES_FILE = Path(OUTPUT_DIR) / "edges.jsonl"
OUT_FILE = Path(OUTPUT_DIR) / "edge_explorer_data.json"


TASK_GROUPS = [
    {"task_id": "task1", "task_name": "Task 1 · Reaction Catalog", "task_desc": "反应目录：反应类型、反应域、反应族",
     "color": "#ef4444",
     "edge_types": ["HAS_REACTION", "IN_DOMAIN", "IN_CLASS", "IN_FAMILY", "INSTANCE_OF_TEMPLATE"]},
    {"task_id": "task2", "task_name": "Task 2 · Catalyst Catalog", "task_desc": "催化剂目录：催化剂、材料平台、活性位、形貌",
     "color": "#22c55e",
     "edge_types": ["HAS_CATALYST", "TESTED_IN", "HAS_MATERIAL_PLATFORM", "HAS_ACTIVE_SITE_FORM",
                    "HAS_MORPHOLOGY_FORM", "HAS_FORM_FACTOR", "INSTANCE_OF_FAMILY"]},
    {"task_id": "task3", "task_name": "Task 3 · Procedure Catalog", "task_desc": "制备流程：合成步骤、步骤类型",
     "color": "#a855f7",
     "edge_types": ["HAS_PROCEDURE", "APPLIES_TO", "SPECIFIC_TO", "HAS_STEP", "NEXT_STEP",
                    "IN_PROCEDURE_TYPE", "IN_STEP_TYPE"]},
    {"task_id": "task4", "task_name": "Task 4 · Characterization", "task_desc": "表征记录：表征方法、样品状态",
     "color": "#06b6d4",
     "edge_types": ["HAS_CHARACTERIZATION", "LINKED_TO_REACTION", "UNDER_SAMPLE_STATE", "USES_METHOD"]},
    {"task_id": "task5", "task_name": "Task 5 · Performance", "task_desc": "性能数据：操作点、指标、目标物种",
     "color": "#f97316",
     "edge_types": ["HAS_PERFORMANCE_DATASET", "HAS_OPERATING_POINT", "HAS_METRIC", "FOR_CATALYST",
                    "UNDER_REACTION", "TESTS_PROPERTY", "TESTS_TARGET_SPECIES", "TESTS_UNDER_BASIS",
                    "UNDER_CATALYST_STATE", "TESTS_PROPERTY_TYPE"]},
    {"task_id": "task6", "task_name": "Task 6 · Mechanistic Claims", "task_desc": "机理主张：证据链、设计机理标签",
     "color": "#ec4899",
     "edge_types": ["HAS_MECHANISTIC_CLAIM", "ABOUT_REACTION", "HAS_EVIDENCE", "SUPPORTED_BY",
                    "HAS_CLAIM_TYPE", "HAS_TAG", "HAS_EVIDENCE_TYPE"]},
    {"task_id": "bridge", "task_name": "Cross-Paper Bridging", "task_desc": "跨论文桥接：本体共现、相似度、共研",
     "color": "#3b82f6",
     "edge_types": ["LIKELY_USES", "LIKELY_ASSOCIATED_WITH", "LIKELY_SUPPORTS",
                    "TESTED_IN_TEMPLATE", "SIMILAR_TO"]},
]


def main():
    if not NODES_FILE.exists():
        sys.exit(f"Missing {NODES_FILE}.")

    nodes = {}
    with open(NODES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            n = json.loads(line)
            nodes[n["uid"]] = n

    edges = []
    with open(EDGES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            edges.append(json.loads(line))

    etype_counts = Counter(e["edge_type"] for e in edges)

    for tg in TASK_GROUPS:
        tg["type_stats"] = sorted(
            ({"edge_type": et, "count": etype_counts.get(et, 0)} for et in tg["edge_types"]),
            key=lambda x: -x["count"],
        )
        tg["total_edges"] = sum(s["count"] for s in tg["type_stats"])

    # APPLIES_TO_CATALYST split (task4 vs task6)
    atc_char = sum(1 for e in edges if e["edge_type"] == "APPLIES_TO_CATALYST" and e["source"].startswith("char:"))
    atc_claim = sum(1 for e in edges if e["edge_type"] == "APPLIES_TO_CATALYST" and e["source"].startswith("claim:"))
    for tg in TASK_GROUPS:
        if tg["task_id"] == "task4":
            tg["type_stats"].append({"edge_type": "APPLIES_TO_CATALYST (from Char)", "count": atc_char})
            tg["total_edges"] += atc_char
        if tg["task_id"] == "task6":
            tg["type_stats"].append({"edge_type": "APPLIES_TO_CATALYST (from Claim)", "count": atc_claim})
            tg["total_edges"] += atc_claim

    # Co-occurrence edges with full detail
    co_occur = []
    for e in edges:
        if e["edge_type"] in ("LIKELY_USES", "LIKELY_ASSOCIATED_WITH", "LIKELY_SUPPORTS"):
            src = nodes.get(e["source"], {})
            tgt = nodes.get(e["target"], {})
            co_occur.append({
                "edge_type": e["edge_type"],
                "source_uid": e["source"], "target_uid": e["target"],
                "source_name": src.get("display_name", e["source"]),
                "target_name": tgt.get("display_name", e["target"]),
                "source_onto_type": src.get("ontology_type", ""),
                "target_onto_type": tgt.get("ontology_type", ""),
                "co_occurrence_count": e.get("co_occurrence_count", 0),
                "witness_paper_count": e.get("witness_paper_count", 0),
                "witness_papers": e.get("witness_papers", []),
                "first_year": e.get("first_year"), "last_year": e.get("last_year"),
            })
    co_occur.sort(key=lambda x: (-x["witness_paper_count"], -x["co_occurrence_count"]))

    paper_titles = {uid: {"title": n.get("title",""), "doi": n.get("doi",""), "year": n.get("year")}
                    for uid, n in nodes.items() if n["node_type"] == "Paper"}

    # Sample edges per type
    edge_samples = {}
    for e in edges:
        et = e["edge_type"]
        edge_samples.setdefault(et, [])
        if len(edge_samples[et]) < 3:
            src = nodes.get(e["source"], {})
            tgt = nodes.get(e["target"], {})
            src_label = src.get("display_name") or src.get("name_reported") or \
                        (src.get("title","")[:50] if src.get("title") else "") or \
                        src.get("local_id") or e["source"]
            tgt_label = tgt.get("display_name") or tgt.get("name_reported") or \
                        (tgt.get("title","")[:50] if tgt.get("title") else "") or \
                        tgt.get("local_id") or e["target"]
            edge_samples[et].append({
                "source": e["source"], "target": e["target"],
                "source_label": src_label, "target_label": tgt_label,
                "source_type": src.get("node_type",""), "target_type": tgt.get("node_type",""),
            })

    out = {
        "task_groups": TASK_GROUPS,
        "co_occur_edges": co_occur,
        "paper_titles": paper_titles,
        "edge_samples": edge_samples,
        "summary": {
            "total_nodes": len(nodes), "total_edges": len(edges),
            "total_edge_types": len(etype_counts),
            "total_co_occur": len(co_occur),
            "cross_paper_co_occur": sum(1 for e in co_occur if e["witness_paper_count"] > 1),
        },
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Wrote {OUT_FILE}  ({len(co_occur)} co-occur edges, {sum(1 for e in co_occur if e['witness_paper_count']>1)} cross-paper)")


if __name__ == "__main__":
    main()
