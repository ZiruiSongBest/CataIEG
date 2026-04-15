"""Paths and constants for the pipeline.

All paths can be overridden via env vars so the same code can process
many shards at once (recommended for 150k-paper scale).

Env vars:
  GRAPH_INPUT_FILE   —— JSONL with task0..task6
  GRAPH_OUTPUT_DIR   —— where nodes/edges/stats/LLM intermediates land
"""
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # catalysis-graph-pipeline/

INPUT_FILE = os.environ.get(
    "GRAPH_INPUT_FILE",
    os.path.join(PIPELINE_ROOT, "sample_6_task.jsonl"),
)
OUTPUT_DIR = os.environ.get(
    "GRAPH_OUTPUT_DIR",
    os.path.join(PIPELINE_ROOT, "graph_output"),
)

NODES_FILE = os.path.join(OUTPUT_DIR, "nodes.jsonl")
EDGES_FILE = os.path.join(OUTPUT_DIR, "edges.jsonl")
STATS_FILE = os.path.join(OUTPUT_DIR, "stats.json")

# CatalystFamily LLM 归一化中间文件
CAT_NAMES_FOR_LLM = os.path.join(OUTPUT_DIR, "catalyst_names_for_llm.json")
CAT_FAMILY_RESULT = os.path.join(OUTPUT_DIR, "catalyst_family_result.json")

# ReactionTemplate LLM 归一化中间文件
RXN_NAMES_FOR_LLM = os.path.join(OUTPUT_DIR, "reaction_names_for_llm.json")
RXN_TEMPLATE_RESULT = os.path.join(OUTPUT_DIR, "reaction_template_result.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalize_doi(doi: str) -> str:
    """DOI 归一化：小写，/ 替换为 _"""
    return doi.lower().replace("/", "_").replace(" ", "")
