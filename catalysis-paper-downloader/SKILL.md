---
name: catalysis-paper-downloader
description: 从学术数据库批量搜索和下载多相催化相关论文 PDF 到本地。当用户需要下载催化论文（如 OER、HER、CO2还原、Fischer-Tropsch 等领域），或提供 DOI 列表要求批量下载，或要求搜索并下载某个催化主题的文献时，必须启用本 Skill。也适用于：催化文献收集、论文 PDF 批量获取、学术论文下载、文献调研准备工作。只要涉及催化相关论文的搜索、筛选和 PDF 下载到本地，都应使用本 Skill。
---

# 催化文献下载 Skill

## 概述

本 Skill 帮助用户从多个学术数据源搜索、筛选和下载多相催化领域的论文 PDF 到本地，按主题分文件夹组织，并生成元数据索引。支持两种模式：关键词搜索下载 和 DOI 批量下载。

## 触发条件

当用户出现以下任意情形时启用：
- 要求下载催化相关论文（电催化、光催化、热催化等）
- 提供一组 DOI 要求批量下载 PDF
- 要求搜索某个催化主题的文献并保存到本地
- 提及 "下载论文"、"收集文献"、"批量下载 PDF"、"paper download" 等关键词
- 需要为后续催化证据图提取做文献准备

---

## 数据源优先级

本 Skill 使用三层数据源，按以下优先级尝试获取 PDF：

1. **Semantic Scholar API**（免费、开放）
   - 用于关键词搜索论文元数据（标题、作者、DOI、摘要等）
   - 部分论文可直接获取开放获取 PDF 链接
   - API 地址：`https://api.semanticscholar.org/graph/v1/paper/search`

2. **CrossRef + Unpaywall**（免费、开放）
   - CrossRef 用于通过 DOI 获取论文元数据
   - Unpaywall 用于查找开放获取版本的 PDF 链接
   - Unpaywall API 地址：`https://api.unpaywall.org/v2/{doi}?email=USER_EMAIL`

3. **Sci-Hub**（灰色地带，作为最后手段）
   - 当以上途径无法获取 PDF 时，可尝试通过 Sci-Hub 获取
   - 用户需自行承担法律风险
   - 使用前必须向用户确认是否允许使用此数据源

---

## 工作流程

### 模式 A：关键词搜索下载

#### Step 1：理解用户需求

与用户确认：
- 搜索关键词（如 "OER catalyst NiFe layered double hydroxide"）
- 想要下载的论文数量上限（默认 20 篇）
- 时间范围（如 2020-2025）
- 是否有特定期刊偏好
- 保存目录路径

#### Step 2：搜索论文

使用 `scripts/search_papers.py` 从 Semantic Scholar 搜索：

```bash
python scripts/search_papers.py search \
  --query "OER catalyst NiFe LDH" \
  --limit 20 \
  --year-range 2020-2025 \
  --output-dir /path/to/topic-folder \
  --output search_results.json
```

脚本会返回论文列表（标题、DOI、作者、年份、摘要、引用数等）。

#### Step 3：筛选论文

将搜索结果呈现给用户，帮助他们筛选：
- 按引用数排序，高引用优先
- 按年份排序，新论文优先
- 根据摘要内容判断相关性
- 排除综述类论文（若用户只需原始研究）

用户确认后生成下载列表。

#### Step 4：下载 PDF

使用 `scripts/search_papers.py` 批量下载：

```bash
python scripts/search_papers.py download \
  --input search_results.json \
  --output-dir /path/to/topic-folder \
  --email user@email.com \
  --use-scihub  # 可选，需用户确认
```

脚本会：
1. 先尝试 Semantic Scholar 开放获取链接
2. 再尝试 Unpaywall 开放获取链接
3. 若用户允许，最后尝试 Sci-Hub
4. 为每篇论文生成规范文件名：`{year}_{first_author}_{short_title}.pdf`
5. 生成 `index.json` 元数据索引

#### Step 5：生成索引报告

下载完成后，在主题文件夹中生成：
- `index.json`：所有论文的结构化元数据
- `download_report.md`：下载结果摘要（成功/失败/跳过统计）

### 模式 B：DOI 批量下载

#### Step 1：获取 DOI 列表

用户可以通过以下方式提供 DOI：
- 直接在聊天中粘贴 DOI 列表
- 提供包含 DOI 的 CSV/TXT/JSON 文件
- 从 BibTeX 文件中提取

#### Step 2：解析并验证 DOI

使用脚本解析并验证 DOI 格式：

```bash
python scripts/search_papers.py from-dois \
  --dois "10.1021/acscatal.xxx,10.1038/s41929-xxx" \
  --output-dir /path/to/topic-folder \
  --email user@email.com
```

或从文件读取：

```bash
python scripts/search_papers.py from-dois \
  --doi-file dois.txt \
  --output-dir /path/to/topic-folder \
  --email user@email.com
```

#### Step 3：下载和索引

同模式 A 的 Step 4 和 Step 5。

---

## 文件组织结构

```
papers/
├── OER_NiFe_LDH/                  # 主题文件夹
│   ├── 2023_Zhang_NiFe_LDH_OER.pdf
│   ├── 2024_Li_FeNi_Hydroxide.pdf
│   ├── index.json                  # 元数据索引
│   └── download_report.md          # 下载报告
├── CO2RR_Cu_catalysts/             # 另一个主题
│   ├── ...
│   └── index.json
└── papers_index.json               # 全局索引（如有多个主题）
```

文件名规范：`{year}_{first_author_lastname}_{abbreviated_title}.pdf`
- 标题截取前 5 个有意义的词
- 空格替换为下划线
- 移除特殊字符

---

## index.json 格式

```json
{
  "topic": "OER NiFe LDH catalysts",
  "download_date": "2026-04-04",
  "papers": [
    {
      "doi": "10.1021/acscatal.3c01234",
      "title": "Full paper title",
      "authors": ["Zhang, X.", "Li, Y."],
      "journal": "ACS Catalysis",
      "year": 2023,
      "abstract": "...",
      "citation_count": 45,
      "filename": "2023_Zhang_NiFe_LDH_OER.pdf",
      "download_status": "success",
      "download_source": "unpaywall",
      "open_access": true
    }
  ],
  "stats": {
    "total": 20,
    "downloaded": 16,
    "failed": 3,
    "skipped": 1
  }
}
```

---

## 注意事项

1. **速率限制**：Semantic Scholar API 每秒限 1 次请求（无 API key）或 10 次（有 key）。脚本内置了限速逻辑。
2. **Unpaywall 邮箱**：Unpaywall API 需要提供邮箱作为标识，请使用用户的邮箱或通用邮箱。
3. **Sci-Hub 可用性**：Sci-Hub 域名经常变动，脚本内置了多个备选域名，但不保证始终可用。使用前必须获得用户明确同意。
4. **版权声明**：通过 Unpaywall 获取的都是合法开放获取版本。Sci-Hub 下载可能涉及版权问题，由用户自行负责。
5. **大批量下载**：超过 50 篇建议分批进行，避免触发 API 限流。
6. **与催化证据图联动**：下载完成后，可直接使用 `catalysis-evidence-graph` Skill 对下载的论文进行结构化数据提取。

---

## 参考文件

- `references/api_guide.md`：各数据源 API 的详细参数说明
- `scripts/search_papers.py`：核心下载脚本
