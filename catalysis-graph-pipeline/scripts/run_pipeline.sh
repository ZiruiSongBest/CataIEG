#!/usr/bin/env bash
# End-to-end pipeline: extract instance + LLM normalize + build graph + viz data.
#
# Usage:
#   GRAPH_INPUT_FILE=/path/to/sample_6_task.jsonl \
#   GRAPH_OUTPUT_DIR=/path/to/graph_output \
#   BLTCY_API_KEY=sk-... \
#   LLM_CONCURRENCY=12 \
#   bash run_pipeline.sh
#
# Flags:
#   --skip-llm-reactions     skip LLM reaction normalization (use fallback)
#   --skip-llm-catalysts     skip LLM catalyst normalization (use rule fallback)
#   --skip-dedup             skip second-pass family dedup
#   --viz-only               regenerate visualization data only (assumes graph already built)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build_graph"
VIZ_DIR="$SCRIPT_DIR/visualize"

SKIP_RXN=0
SKIP_CAT=0
SKIP_DEDUP=0
VIZ_ONLY=0
for arg in "$@"; do
  case $arg in
    --skip-llm-reactions) SKIP_RXN=1 ;;
    --skip-llm-catalysts) SKIP_CAT=1 ;;
    --skip-dedup) SKIP_DEDUP=1 ;;
    --viz-only) VIZ_ONLY=1 ;;
    *) echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

: "${GRAPH_INPUT_FILE:?GRAPH_INPUT_FILE must be set}"
: "${GRAPH_OUTPUT_DIR:?GRAPH_OUTPUT_DIR must be set}"
mkdir -p "$GRAPH_OUTPUT_DIR"

export PYTHONPATH="$BUILD_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [ $VIZ_ONLY -eq 0 ]; then
  echo "==== Step 1/5: initial graph build (exports LLM inputs, uses fallback) ===="
  python3 "$BUILD_DIR/main.py"

  if [ $SKIP_RXN -eq 0 ]; then
    echo ""
    echo "==== Step 2/5: LLM reaction normalization ===="
    python3 "$BUILD_DIR/llm_normalize_reactions.py"
  fi

  if [ $SKIP_CAT -eq 0 ]; then
    echo ""
    echo "==== Step 3/5: LLM catalyst normalization (first pass) ===="
    python3 "$BUILD_DIR/llm_normalize_catalysts.py"
  fi

  if [ $SKIP_DEDUP -eq 0 ] && [ $SKIP_CAT -eq 0 ]; then
    echo ""
    echo "==== Step 4/5: family-level dedup (second pass) ===="
    python3 "$BUILD_DIR/llm_dedup_catalyst_families.py"
  fi

  echo ""
  echo "==== Step 5/5: rebuild graph with LLM results ===="
  python3 "$BUILD_DIR/main.py"
fi

echo ""
echo "==== Generating visualization data ===="
python3 "$VIZ_DIR/gen_case_review_data.py"
python3 "$VIZ_DIR/gen_edge_explorer_data.py"
bash "$VIZ_DIR/publish_viz.sh"

echo ""
echo "Pipeline done. Outputs in: $GRAPH_OUTPUT_DIR"
