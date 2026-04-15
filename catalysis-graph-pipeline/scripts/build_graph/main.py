"""催化证据图构建 —— 主流程"""
from collections import Counter
import json
import sys
import time

from config import INPUT_FILE, NODES_FILE, EDGES_FILE, STATS_FILE
from phase1_instance import build_instance_layer
from phase2_ontology import build_ontology_layer
from phase3a_rxn_template import build_reaction_templates
from phase3b_cat_family import build_catalyst_families
from phase4_bridge import build_co_studied_edges, build_template_family_edges, build_similarity_edges
from stats import generate_stats, print_stats


def load_papers(path: str) -> list[dict]:
    papers = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            papers.append(json.loads(line))
    print(f"加载 {len(papers)} 篇论文")
    return papers


def deduplicate_edges(edges: list[dict]) -> list[dict]:
    """去重：(source, target, edge_type) 相同的边只保留第一条"""
    seen = set()
    deduped = []
    for e in edges:
        key = (e["source"], e["target"], e["edge_type"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped


def validate_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """验证边的 source 和 target 都指向存在的节点，去除悬挂边"""
    valid_uids = {n["uid"] for n in nodes}
    valid_edges = []
    dangling = 0
    for e in edges:
        if e["source"] in valid_uids and e["target"] in valid_uids:
            valid_edges.append(e)
        else:
            dangling += 1
    if dangling:
        print(f"  移除 {dangling} 条悬挂边（source/target 不存在）")
    return valid_edges


def validate_unique_nodes(nodes: list[dict]):
    """验证节点 UID 全局唯一，避免不同实例被错误别名化"""
    counts = Counter(n["uid"] for n in nodes)
    duplicates = [uid for uid, count in counts.items() if count > 1]
    if duplicates:
        sample = ", ".join(duplicates[:10])
        raise ValueError(f"发现 {len(duplicates)} 个重复节点 UID，示例: {sample}")


def write_jsonl(data: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            # 序列化时把 set 转为 list
            cleaned = {}
            for k, v in item.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, set):
                    cleaned[k] = sorted(v)
                else:
                    cleaned[k] = v
            f.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
    print(f"  写入 {path} ({len(data)} 条)")


def main():
    t0 = time.time()

    # 加载数据
    papers = load_papers(INPUT_FILE)

    # Phase 1: 实例层
    print("\n[Phase 1] 构建实例层...")
    instance_nodes, instance_edges = build_instance_layer(papers)
    print(f"  节点: {len(instance_nodes)}, 边: {len(instance_edges)}")

    # Phase 2: 本体层
    print("\n[Phase 2] 构建本体层...")
    onto_nodes, onto_edges = build_ontology_layer(instance_nodes)
    print(f"  本体节点: {len(onto_nodes)}, 映射边: {len(onto_edges)}")

    # 合并 Phase 1+2
    all_nodes = instance_nodes + onto_nodes
    all_edges = instance_edges + onto_edges

    # Phase 3a: ReactionTemplate
    print("\n[Phase 3a] 归并 ReactionTemplate...")
    rxn_tmpl_nodes, rxn_tmpl_edges = build_reaction_templates(instance_nodes)
    print(f"  模板数: {len(rxn_tmpl_nodes)}, 边: {len(rxn_tmpl_edges)}")
    all_nodes.extend(rxn_tmpl_nodes)
    all_edges.extend(rxn_tmpl_edges)

    # Phase 3b: CatalystFamily
    print("\n[Phase 3b] 归并 CatalystFamily...")
    cat_fam_nodes, cat_fam_edges = build_catalyst_families(instance_nodes)
    print(f"  家族数: {len(cat_fam_nodes)}, 边: {len(cat_fam_edges)}")
    all_nodes.extend(cat_fam_nodes)
    all_edges.extend(cat_fam_edges)

    # Phase 4a: 本体共现边
    print("\n[Phase 4a] 构建本体共现边 (CO_STUDIED_WITH)...")
    co_edges = build_co_studied_edges(papers, all_nodes, all_edges)
    print(f"  共现边: {len(co_edges)}")
    all_edges.extend(co_edges)

    # Phase 4b: 规范化实体共研边
    print("\n[Phase 4b] 构建 CatalystFamily ↔ ReactionTemplate 共研边...")
    tf_edges = build_template_family_edges(all_nodes, all_edges)
    print(f"  共研边: {len(tf_edges)}")
    all_edges.extend(tf_edges)

    # Phase 4c: 相似度边
    print("\n[Phase 4c] 构建相似度边 (SIMILAR_TO)...")
    sim_edges = build_similarity_edges(all_nodes)
    print(f"  相似边: {len(sim_edges)}")
    all_edges.extend(sim_edges)

    # 后处理：去重 + 验证
    print("\n[后处理] 去重和验证...")
    validate_unique_nodes(all_nodes)
    all_edges = deduplicate_edges(all_edges)
    all_edges = validate_edges(all_nodes, all_edges)
    print(f"  最终: {len(all_nodes)} 节点, {len(all_edges)} 边")

    # 写入文件
    print("\n[输出]")
    write_jsonl(all_nodes, NODES_FILE)
    write_jsonl(all_edges, EDGES_FILE)

    # 统计
    s = generate_stats(all_nodes, all_edges)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print_stats(s)

    elapsed = time.time() - t0
    print(f"总耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
