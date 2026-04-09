#!/bin/bash
# ============================================================
# OER 电催化论文批量下载脚本
# 在本地终端运行此脚本即可下载 10 篇论文
# ============================================================

# 确保安装了 requests 库
pip install requests -q

# 设置路径（根据你的实际路径修改）
SCRIPT_DIR="$(dirname "$0")/../catalysis-paper-downloader/scripts"
OUTPUT_DIR="$(dirname "$0")/OER_electrocatalysis"

# 10 篇 OER 电催化相关论文 DOI
DOIS="10.1021/acsaem.2c01115,\
10.1021/acsami.4c03766,\
10.1021/acsanm.3c01002,\
10.1021/acsomega.4c11115,\
10.1021/acsanm.3c03087,\
10.1002/advs.202401975,\
10.1021/acsmaterialsau.4c00086,\
10.1021/acs.energyfuels.4c03780,\
10.3389/fenrg.2024.1373522,\
10.1038/s41598-021-04347-9"

echo "📦 开始下载 OER 电催化论文..."
echo "📁 输出目录: $OUTPUT_DIR"
echo ""

python "$SCRIPT_DIR/search_papers.py" from-dois \
  --dois "$DOIS" \
  --output-dir "$OUTPUT_DIR" \
  --email "zzs144118@gmail.com" \
  --use-scihub \
  --topic "OER NiFe LDH electrocatalysis"

echo ""
echo "✅ 完成！下载完成后可以回到 Cowork 运行催化证据图提取。"
