#!/usr/bin/env bash
# Publish visualization assets into the output directory.
#
# After running the pipeline, run this to copy case-review.html and
# edge-explorer.html next to the generated paper_bundles.json /
# edge_explorer_data.json so they can be opened directly in a browser.
set -eu

: "${GRAPH_OUTPUT_DIR:=graph_output}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ASSETS_DIR="$PIPELINE_ROOT/assets"

mkdir -p "$GRAPH_OUTPUT_DIR"
cp "$ASSETS_DIR/case-review.html" "$GRAPH_OUTPUT_DIR/"
cp "$ASSETS_DIR/edge-explorer.html" "$GRAPH_OUTPUT_DIR/"

echo "Published visualization HTML to $GRAPH_OUTPUT_DIR"
echo "Open:"
echo "  $GRAPH_OUTPUT_DIR/case-review.html     (uses paper_bundles.json)"
echo "  $GRAPH_OUTPUT_DIR/edge-explorer.html   (uses edge_explorer_data.json)"
