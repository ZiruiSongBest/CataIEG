"""路径和常量配置"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE = os.path.join(BASE_DIR, "sample_6_task.jsonl")
OUTPUT_DIR = os.path.join(BASE_DIR, "graph_output")
NODES_FILE = os.path.join(OUTPUT_DIR, "nodes.jsonl")
EDGES_FILE = os.path.join(OUTPUT_DIR, "edges.jsonl")
STATS_FILE = os.path.join(OUTPUT_DIR, "stats.json")

# CatalystFamily LLM 归一化中间文件
CAT_NAMES_FOR_LLM = os.path.join(OUTPUT_DIR, "catalyst_names_for_llm.json")
CAT_FAMILY_RESULT = os.path.join(OUTPUT_DIR, "catalyst_family_result.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalize_doi(doi: str) -> str:
    """DOI 归一化：小写，/ 替换为 _"""
    return doi.lower().replace("/", "_").replace(" ", "")
