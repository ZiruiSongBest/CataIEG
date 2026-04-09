# API 参考指南

## 1. Semantic Scholar API

### 论文搜索
- **端点**: `GET https://api.semanticscholar.org/graph/v1/paper/search`
- **参数**:
  - `query`: 搜索关键词（必填）
  - `limit`: 每页结果数，最大 100
  - `offset`: 分页偏移量
  - `year`: 年份范围，如 `2020-2025`
  - `fields`: 返回字段，常用: `paperId,externalIds,title,authors,year,abstract,citationCount,journal,isOpenAccess,openAccessPdf`
- **速率限制**: 无 API key 每秒 1 次，有 key 每秒 10 次
- **申请 API key**: https://www.semanticscholar.org/product/api#api-key

### 通过 DOI 获取论文
- **端点**: `GET https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}`
- **参数**: `fields` 同上

## 2. CrossRef API

### 通过 DOI 获取元数据
- **端点**: `GET https://api.crossref.org/works/{doi}`
- **推荐 Header**: `User-Agent: AppName/Version (mailto:your@email.com)`
- **速率限制**: 礼貌池（polite pool）需提供邮箱联系方式

## 3. Unpaywall API

### 查找开放获取 PDF
- **端点**: `GET https://api.unpaywall.org/v2/{doi}?email={your_email}`
- **关键返回字段**:
  - `best_oa_location.url_for_pdf`: 最佳开放获取 PDF 链接
  - `oa_locations[]`: 所有开放获取位置列表
- **要求**: 必须提供有效邮箱

## 4. Sci-Hub

### 获取论文 PDF
- **URL 模式**: `https://sci-hub.se/{doi}`
- **注意事项**:
  - 域名经常变动，需维护备选列表
  - 返回 HTML 页面，需从中解析实际 PDF 链接
  - 存在法律风险，仅在用户明确同意后使用
  - 部分地区可能无法访问
