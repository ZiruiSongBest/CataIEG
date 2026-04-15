"""统计报告生成"""
import json
from collections import Counter


def generate_stats(nodes: list[dict], edges: list[dict]) -> dict:
    node_types = Counter(n["node_type"] for n in nodes)
    edge_types = Counter(e["edge_type"] for e in edges)

    # 本体统计
    onto_nodes = [n for n in nodes if n["node_type"] == "OntologyTerm"]
    onto_by_type = Counter(n["ontology_type"] for n in onto_nodes)

    # 共现边统计
    co_studied = [e for e in edges if e["edge_type"] == "CO_STUDIED_WITH"]
    co_studied_avg_count = (
        sum(e["co_occurrence_count"] for e in co_studied) / len(co_studied)
        if co_studied else 0
    )

    # Template/Family 统计
    templates = [n for n in nodes if n["node_type"] == "ReactionTemplate"]
    families = [n for n in nodes if n["node_type"] == "CatalystFamily"]

    template_sizes = [n["instance_count"] for n in templates]
    family_sizes = [n["instance_count"] for n in families]

    stats = {
        "summary": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "unique_node_types": len(node_types),
            "unique_edge_types": len(edge_types),
        },
        "nodes_by_type": dict(node_types.most_common()),
        "edges_by_type": dict(edge_types.most_common()),
        "ontology_terms_by_type": dict(onto_by_type.most_common()),
        "reaction_templates": {
            "count": len(templates),
            "avg_instances": sum(template_sizes) / len(template_sizes) if template_sizes else 0,
            "max_instances": max(template_sizes) if template_sizes else 0,
            "singleton_count": sum(1 for s in template_sizes if s == 1),
        },
        "catalyst_families": {
            "count": len(families),
            "avg_instances": sum(family_sizes) / len(family_sizes) if family_sizes else 0,
            "max_instances": max(family_sizes) if family_sizes else 0,
            "singleton_count": sum(1 for s in family_sizes if s == 1),
        },
        "co_studied_edges": {
            "count": len(co_studied),
            "avg_co_occurrence": round(co_studied_avg_count, 2),
        },
        "similarity_edges": {
            "count": sum(1 for e in edges if e["edge_type"] == "SIMILAR_TO"),
        },
        "tested_in_template_edges": {
            "count": sum(1 for e in edges if e["edge_type"] == "TESTED_IN_TEMPLATE"),
        },
    }
    return stats


def print_stats(stats: dict):
    print("\n" + "=" * 60)
    print("  催化证据图 构建完成")
    print("=" * 60)

    s = stats["summary"]
    print(f"\n  总节点数: {s['total_nodes']}")
    print(f"  总边数:   {s['total_edges']}")
    print(f"  节点类型: {s['unique_node_types']}")
    print(f"  边类型:   {s['unique_edge_types']}")

    print("\n--- 节点分布 ---")
    for nt, count in stats["nodes_by_type"].items():
        print(f"  {nt:30s} {count:>6d}")

    print("\n--- 边分布 ---")
    for et, count in stats["edges_by_type"].items():
        print(f"  {et:30s} {count:>6d}")

    print("\n--- 本体节点分布 ---")
    for ot, count in stats["ontology_terms_by_type"].items():
        print(f"  {ot:30s} {count:>6d}")

    rt = stats["reaction_templates"]
    print(f"\n--- ReactionTemplate ---")
    print(f"  模板数: {rt['count']} (单例: {rt['singleton_count']})")
    print(f"  平均实例数: {rt['avg_instances']:.1f}, 最大: {rt['max_instances']}")

    cf = stats["catalyst_families"]
    print(f"\n--- CatalystFamily ---")
    print(f"  家族数: {cf['count']} (单例: {cf['singleton_count']})")
    print(f"  平均实例数: {cf['avg_instances']:.1f}, 最大: {cf['max_instances']}")

    co = stats["co_studied_edges"]
    print(f"\n--- 跨文献桥接 ---")
    print(f"  CO_STUDIED_WITH 边数: {co['count']} (平均共现: {co['avg_co_occurrence']})")
    print(f"  SIMILAR_TO 边数: {stats['similarity_edges']['count']}")
    print(f"  TESTED_IN_TEMPLATE 边数: {stats['tested_in_template_edges']['count']}")
    print()
