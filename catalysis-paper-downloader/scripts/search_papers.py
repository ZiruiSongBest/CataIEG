#!/usr/bin/env python3
"""
Catalysis Paper Downloader
搜索、筛选和下载多相催化领域论文 PDF。

支持三种数据源：
  1. Semantic Scholar API（搜索 + 开放获取下载）
  2. CrossRef + Unpaywall（DOI 元数据 + 开放获取 PDF）
  3. Sci-Hub（最后手段，需用户确认）

使用方式：
  # 关键词搜索
  python search_papers.py search --query "OER NiFe LDH" --limit 20 --output-dir ./papers/OER

  # DOI 批量下载
  python search_papers.py from-dois --dois "10.1021/xxx,10.1038/yyy" --output-dir ./papers/topic

  # 从文件读取 DOI
  python search_papers.py from-dois --doi-file dois.txt --output-dir ./papers/topic

  # 下载已有搜索结果
  python search_papers.py download --input search_results.json --output-dir ./papers/topic
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

# ─── 配置 ───────────────────────────────────────────────────────────────────

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
CROSSREF_API = "https://api.crossref.org/works"

# Sci-Hub 备选域名（经常变动，按需更新）
SCIHUB_DOMAINS = [
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
]

DEFAULT_EMAIL = "catalysis-downloader@example.com"
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 1.1  # Semantic Scholar 无 key 限速

# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def sanitize_filename(text: str, max_words: int = 5) -> str:
    """将标题转为安全文件名片段。"""
    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # NFD 归一化并移除非 ASCII
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # 只保留字母数字和空格
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    words = text.split()
    # 过滤停用词
    stopwords = {"the", "a", "an", "of", "in", "on", "for", "and", "with", "by", "to", "from", "at", "is", "are", "was", "were"}
    meaningful = [w for w in words if w.lower() not in stopwords]
    if not meaningful:
        meaningful = words
    return "_".join(meaningful[:max_words])


def make_pdf_filename(paper: dict) -> str:
    """生成标准 PDF 文件名: {year}_{first_author}_{short_title}.pdf"""
    year = paper.get("year", "unknown")
    authors = paper.get("authors", [])
    if authors:
        first = authors[0] if isinstance(authors[0], str) else authors[0].get("name", "Unknown")
        last_name = first.split(",")[0].split()[-1] if first else "Unknown"
    else:
        last_name = "Unknown"
    title_part = sanitize_filename(paper.get("title", "untitled"))
    filename = f"{year}_{last_name}_{title_part}.pdf"
    # 限制长度
    if len(filename) > 120:
        filename = filename[:116] + ".pdf"
    return filename


def safe_request(url: str, headers: dict = None, timeout: int = REQUEST_TIMEOUT, stream: bool = False):
    """带重试的 HTTP GET 请求。"""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, stream=stream, allow_redirects=True)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                print(f"  ⏳ 速率限制，等待 {wait}s ...")
                time.sleep(wait)
                continue
            return resp
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                print(f"  ❌ 请求失败: {e}")
                return None
            time.sleep(1)
    return None


# ─── Semantic Scholar ─────────────────────────────────────────────────────────

def search_semantic_scholar(query: str, limit: int = 20, year_range: str = None, api_key: str = None) -> list:
    """通过 Semantic Scholar API 搜索论文。"""
    papers = []
    offset = 0
    batch_size = min(limit, 100)
    fields = "paperId,externalIds,title,authors,year,abstract,citationCount,journal,isOpenAccess,openAccessPdf"

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    while len(papers) < limit:
        params = f"query={quote(query)}&limit={batch_size}&offset={offset}&fields={fields}"
        if year_range:
            params += f"&year={year_range}"

        url = f"{SEMANTIC_SCHOLAR_API}/paper/search?{params}"
        print(f"  🔍 搜索 Semantic Scholar (offset={offset}) ...")
        resp = safe_request(url, headers=headers)

        if not resp or resp.status_code != 200:
            print(f"  ⚠️ Semantic Scholar 搜索失败: {resp.status_code if resp else 'no response'}")
            break

        data = resp.json()
        results = data.get("data", [])
        if not results:
            break

        for r in results:
            doi = (r.get("externalIds") or {}).get("DOI")
            oa_pdf = (r.get("openAccessPdf") or {}).get("url")
            authors_list = [a.get("name", "") for a in (r.get("authors") or [])]
            journal_name = (r.get("journal") or {}).get("name", "")

            papers.append({
                "paperId": r.get("paperId"),
                "doi": doi,
                "title": r.get("title", ""),
                "authors": authors_list,
                "year": r.get("year"),
                "abstract": r.get("abstract", ""),
                "citation_count": r.get("citationCount", 0),
                "journal": journal_name,
                "is_open_access": r.get("isOpenAccess", False),
                "oa_pdf_url": oa_pdf,
                "download_status": "pending",
                "download_source": None,
                "filename": None,
            })

        offset += batch_size
        if data.get("total", 0) <= offset:
            break
        time.sleep(RATE_LIMIT_DELAY)

    return papers[:limit]


# ─── CrossRef + Unpaywall ────────────────────────────────────────────────────

def get_metadata_crossref(doi: str) -> dict:
    """通过 CrossRef 获取论文元数据。"""
    url = f"{CROSSREF_API}/{doi}"
    resp = safe_request(url, headers={"User-Agent": "CatalysisDownloader/1.0 (mailto:catalysis@example.com)"})
    if not resp or resp.status_code != 200:
        return {}
    data = resp.json().get("message", {})
    authors = []
    for a in data.get("author", []):
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)
    title_list = data.get("title", [])
    title = title_list[0] if title_list else ""
    year = None
    date_parts = (data.get("published-print") or data.get("published-online") or {}).get("date-parts", [[]])
    if date_parts and date_parts[0]:
        year = date_parts[0][0]
    journal_list = data.get("container-title", [])
    journal = journal_list[0] if journal_list else ""

    return {
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "abstract": data.get("abstract", ""),
        "citation_count": data.get("is-referenced-by-count", 0),
    }


def get_unpaywall_pdf(doi: str, email: str = DEFAULT_EMAIL) -> str | None:
    """通过 Unpaywall 查找开放获取 PDF 链接。"""
    url = f"{UNPAYWALL_API}/{doi}?email={email}"
    resp = safe_request(url)
    if not resp or resp.status_code != 200:
        return None
    data = resp.json()
    best = data.get("best_oa_location") or {}
    pdf_url = best.get("url_for_pdf") or best.get("url")
    if pdf_url and pdf_url.endswith(".pdf"):
        return pdf_url
    # 遍历所有 OA location
    for loc in data.get("oa_locations", []):
        u = loc.get("url_for_pdf")
        if u:
            return u
    return None


# ─── Sci-Hub ──────────────────────────────────────────────────────────────────

def get_scihub_pdf(doi: str) -> str | None:
    """尝试从 Sci-Hub 获取 PDF 下载链接。"""
    for domain in SCIHUB_DOMAINS:
        url = f"{domain}/{doi}"
        try:
            resp = requests.get(url, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                continue
            # 尝试从页面中提取 PDF 链接
            # Sci-Hub 页面中通常有一个 iframe 或 embed 指向 PDF
            match = re.search(r'(https?://[^\s"\'<>]+\.pdf)', resp.text)
            if match:
                pdf_url = match.group(1)
                return pdf_url
            # 有时 src 属性以 // 开头
            match = re.search(r'src\s*=\s*["\']?(//[^\s"\'<>]+\.pdf)', resp.text)
            if match:
                return "https:" + match.group(1)
        except Exception:
            continue
    return None


# ─── PDF 下载 ─────────────────────────────────────────────────────────────────

def download_pdf(url: str, filepath: str) -> bool:
    """下载 PDF 文件到指定路径。"""
    resp = safe_request(url, stream=True)
    if not resp or resp.status_code != 200:
        return False
    # 检查是否真的是 PDF
    content_type = resp.headers.get("Content-Type", "")
    first_bytes = b""
    try:
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if not first_bytes:
                    first_bytes = chunk[:5]
                f.write(chunk)
        # 验证 PDF 头
        if first_bytes[:4] != b"%PDF":
            os.remove(filepath)
            return False
        return True
    except Exception as e:
        print(f"  ❌ 写入失败: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return False


def download_paper(paper: dict, output_dir: str, email: str = DEFAULT_EMAIL, use_scihub: bool = False) -> dict:
    """尝试通过多个数据源下载论文 PDF。"""
    doi = paper.get("doi")
    filename = make_pdf_filename(paper)
    paper["filename"] = filename
    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath):
        paper["download_status"] = "skipped_exists"
        paper["download_source"] = "local"
        print(f"  ⏭️  已存在: {filename}")
        return paper

    title_short = paper.get("title", "")[:60]
    print(f"  📥 下载中: {title_short}...")

    # 1. 尝试 Semantic Scholar OA 链接
    oa_url = paper.get("oa_pdf_url")
    if oa_url:
        print(f"    → 尝试 Semantic Scholar OA ...")
        if download_pdf(oa_url, filepath):
            paper["download_status"] = "success"
            paper["download_source"] = "semantic_scholar_oa"
            print(f"    ✅ 成功 (Semantic Scholar OA)")
            return paper

    # 2. 尝试 Unpaywall
    if doi:
        print(f"    → 尝试 Unpaywall ...")
        unpaywall_url = get_unpaywall_pdf(doi, email)
        if unpaywall_url:
            if download_pdf(unpaywall_url, filepath):
                paper["download_status"] = "success"
                paper["download_source"] = "unpaywall"
                print(f"    ✅ 成功 (Unpaywall)")
                return paper

    # 3. 尝试 Sci-Hub（如果允许）
    if use_scihub and doi:
        print(f"    → 尝试 Sci-Hub ...")
        scihub_url = get_scihub_pdf(doi)
        if scihub_url:
            if download_pdf(scihub_url, filepath):
                paper["download_status"] = "success"
                paper["download_source"] = "scihub"
                print(f"    ✅ 成功 (Sci-Hub)")
                return paper

    paper["download_status"] = "failed"
    print(f"    ❌ 所有数据源均失败")
    return paper


# ─── 批量操作 ─────────────────────────────────────────────────────────────────

def batch_download(papers: list, output_dir: str, email: str = DEFAULT_EMAIL, use_scihub: bool = False) -> list:
    """批量下载论文列表。"""
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for i, paper in enumerate(papers):
        print(f"\n[{i+1}/{len(papers)}]")
        result = download_paper(paper, output_dir, email, use_scihub)
        results.append(result)
        time.sleep(RATE_LIMIT_DELAY)
    return results


def generate_index(papers: list, topic: str, output_dir: str):
    """生成 index.json 和 download_report.md。"""
    stats = {
        "total": len(papers),
        "downloaded": sum(1 for p in papers if p["download_status"] == "success"),
        "failed": sum(1 for p in papers if p["download_status"] == "failed"),
        "skipped": sum(1 for p in papers if p["download_status"].startswith("skipped")),
    }

    index = {
        "topic": topic,
        "download_date": datetime.now().strftime("%Y-%m-%d"),
        "papers": papers,
        "stats": stats,
    }

    index_path = os.path.join(output_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\n📋 索引已保存: {index_path}")

    # 生成下载报告
    report_lines = [
        f"# 下载报告: {topic}",
        f"\n日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"\n## 统计",
        f"- 总计: {stats['total']}",
        f"- 成功下载: {stats['downloaded']}",
        f"- 下载失败: {stats['failed']}",
        f"- 跳过（已存在）: {stats['skipped']}",
        f"\n## 论文列表\n",
    ]

    for i, p in enumerate(papers, 1):
        status_icon = {"success": "✅", "failed": "❌", "skipped_exists": "⏭️"}.get(p["download_status"], "❓")
        source = p.get("download_source", "N/A")
        report_lines.append(f"{i}. {status_icon} **{p.get('title', 'N/A')}**")
        report_lines.append(f"   - DOI: {p.get('doi', 'N/A')}")
        report_lines.append(f"   - 来源: {source} | 文件: {p.get('filename', 'N/A')}")
        report_lines.append("")

    report_path = os.path.join(output_dir, "download_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"📝 报告已保存: {report_path}")

    return index


def resolve_dois(dois: list, email: str = DEFAULT_EMAIL) -> list:
    """通过 DOI 列表获取论文元数据。"""
    papers = []
    for i, doi in enumerate(dois):
        doi = doi.strip()
        if not doi:
            continue
        print(f"  [{i+1}/{len(dois)}] 解析 DOI: {doi}")

        # 先尝试 Semantic Scholar
        url = f"{SEMANTIC_SCHOLAR_API}/paper/DOI:{doi}?fields=paperId,externalIds,title,authors,year,abstract,citationCount,journal,isOpenAccess,openAccessPdf"
        resp = safe_request(url)
        if resp and resp.status_code == 200:
            r = resp.json()
            authors_list = [a.get("name", "") for a in (r.get("authors") or [])]
            journal_name = (r.get("journal") or {}).get("name", "")
            oa_pdf = (r.get("openAccessPdf") or {}).get("url")
            papers.append({
                "paperId": r.get("paperId"),
                "doi": doi,
                "title": r.get("title", ""),
                "authors": authors_list,
                "year": r.get("year"),
                "abstract": r.get("abstract", ""),
                "citation_count": r.get("citationCount", 0),
                "journal": journal_name,
                "is_open_access": r.get("isOpenAccess", False),
                "oa_pdf_url": oa_pdf,
                "download_status": "pending",
                "download_source": None,
                "filename": None,
            })
        else:
            # 回退到 CrossRef
            meta = get_metadata_crossref(doi)
            if meta:
                meta.update({
                    "paperId": None,
                    "is_open_access": False,
                    "oa_pdf_url": None,
                    "download_status": "pending",
                    "download_source": None,
                    "filename": None,
                })
                papers.append(meta)
            else:
                papers.append({
                    "doi": doi,
                    "title": f"Unknown ({doi})",
                    "authors": [],
                    "year": None,
                    "abstract": "",
                    "citation_count": 0,
                    "journal": "",
                    "is_open_access": False,
                    "oa_pdf_url": None,
                    "download_status": "pending",
                    "download_source": None,
                    "filename": None,
                })
        time.sleep(RATE_LIMIT_DELAY)

    return papers


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="催化论文搜索与下载工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # search 子命令
    sp_search = subparsers.add_parser("search", help="关键词搜索论文")
    sp_search.add_argument("--query", "-q", required=True, help="搜索关键词")
    sp_search.add_argument("--limit", "-n", type=int, default=20, help="最大结果数 (默认 20)")
    sp_search.add_argument("--year-range", help="年份范围，如 2020-2025")
    sp_search.add_argument("--output-dir", "-o", required=True, help="输出目录")
    sp_search.add_argument("--output", default="search_results.json", help="搜索结果文件名")
    sp_search.add_argument("--api-key", help="Semantic Scholar API key (可选)")

    # download 子命令
    sp_dl = subparsers.add_parser("download", help="从搜索结果下载 PDF")
    sp_dl.add_argument("--input", "-i", required=True, help="搜索结果 JSON 文件")
    sp_dl.add_argument("--output-dir", "-o", required=True, help="输出目录")
    sp_dl.add_argument("--email", default=DEFAULT_EMAIL, help="Unpaywall 邮箱")
    sp_dl.add_argument("--use-scihub", action="store_true", help="允许使用 Sci-Hub")
    sp_dl.add_argument("--topic", default="", help="主题名称（用于索引）")

    # from-dois 子命令
    sp_dois = subparsers.add_parser("from-dois", help="从 DOI 列表下载")
    sp_dois.add_argument("--dois", help="逗号分隔的 DOI 列表")
    sp_dois.add_argument("--doi-file", help="包含 DOI 的文件（每行一个）")
    sp_dois.add_argument("--output-dir", "-o", required=True, help="输出目录")
    sp_dois.add_argument("--email", default=DEFAULT_EMAIL, help="Unpaywall 邮箱")
    sp_dois.add_argument("--use-scihub", action="store_true", help="允许使用 Sci-Hub")
    sp_dois.add_argument("--topic", default="", help="主题名称")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "search":
        print(f"🔎 搜索: {args.query}")
        papers = search_semantic_scholar(
            query=args.query,
            limit=args.limit,
            year_range=args.year_range,
            api_key=args.api_key,
        )
        print(f"  找到 {len(papers)} 篇论文")
        os.makedirs(args.output_dir, exist_ok=True)
        out_path = os.path.join(args.output_dir, args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"  💾 结果已保存: {out_path}")

        # 打印简要列表
        for i, p in enumerate(papers, 1):
            print(f"  {i:3d}. [{p.get('year', '?')}] (引用:{p.get('citation_count', 0):>4d}) {p.get('title', '')[:80]}")

    elif args.command == "download":
        with open(args.input, "r", encoding="utf-8") as f:
            papers = json.load(f)
        print(f"📦 准备下载 {len(papers)} 篇论文 → {args.output_dir}")
        results = batch_download(papers, args.output_dir, args.email, args.use_scihub)
        topic = args.topic or Path(args.output_dir).name
        generate_index(results, topic, args.output_dir)

    elif args.command == "from-dois":
        dois = []
        if args.dois:
            dois = [d.strip() for d in args.dois.split(",")]
        elif args.doi_file:
            with open(args.doi_file, "r") as f:
                content = f.read()
                # 支持逗号或换行分隔
                dois = [d.strip() for d in re.split(r"[,\n]", content) if d.strip()]
        else:
            print("❌ 请提供 --dois 或 --doi-file")
            sys.exit(1)

        print(f"📋 解析 {len(dois)} 个 DOI ...")
        papers = resolve_dois(dois, args.email)
        print(f"\n📦 开始下载 → {args.output_dir}")
        results = batch_download(papers, args.output_dir, args.email, args.use_scihub)
        topic = args.topic or Path(args.output_dir).name
        generate_index(results, topic, args.output_dir)

    print("\n✨ 完成!")


if __name__ == "__main__":
    main()
