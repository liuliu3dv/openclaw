---
name: arxiv
description: Search, download, and read arXiv papers. Use when: (1) searching for academic papers on arXiv, (2) downloading paper PDFs, (3) reading paper abstracts and metadata, (4) staying updated with papers in specific fields (cs, physics, math, etc.)
homepage: https://arxiv.org
metadata:
  {
    "openclaw":
      {
        "emoji": "📄",
        "requires": { "bins": ["python3", "uv"], "env": ["MINIMAX_API_KEY"] },
        "primaryEnv": "MINIMAX_API_KEY",
        "install":
          [
            {
              "id": "python-brew",
              "kind": "brew",
              "formula": "python",
              "bins": ["python3"],
              "label": "Install Python (brew)",
            },
            {
              "id": "uv-brew",
              "kind": "brew",
              "formula": "uv",
              "bins": ["uv"],
              "label": "Install uv (brew)",
            },
          ],
      },
  }
---

# arXiv Skill

搜索、下载和阅读 arXiv 论文。

## 每日论文速览 (带LLM分析)

生成每日论文报告,包含LLM深度分析:

```bash
# 基础用法
uv run scripts/daily_arxiv.py

# 自定义分类
uv run scripts/daily_arxiv.py --categories cs.CL,cs.CV,cs.LG

# 自定义每个分类的论文数量
uv run scripts/daily_arxiv.py --max-results 5

# 自定义模型和PDF页数
uv run scripts/daily_arxiv.py --model MiniMax-M2.5 --max-pages 10

# 强制重新处理(忽略缓存)
uv run scripts/daily_arxiv.py --force
```

### 配置

在 `~/.openclaw/openclaw.json` 中配置:

```json
{
  "skills": {
    "arxiv": {
      "apiKey": "your-minimax-api-key",
      "model": "MiniMax-M2.5",
      "maxPages": 8,
      "maxResults": 3,
      "categories": ["cs.CL", "cs.CV", "cs.LG", "cs.AI", "stat.ML"]
    }
  }
}
```

或使用环境变量:

```bash
export MINIMAX_API_KEY="your-key-here"
```

优先级: `--api-key` > 环境变量 > 配置文件

### 输出

- Markdown报告: `~/arxiv-daily/YYYY-MM-DD.md`
- PDF缓存: `~/arxiv-daily/pdfs/`
- JSON缓存: `~/arxiv-daily/cache/`

## 安装依赖

使用 `uv` 自动管理依赖(推荐):

```bash
# uv 会自动安装 arxiv 和 pymupdf
uv run scripts/daily_arxiv.py
```

或手动安装:

```bash
pip install arxiv pymupdf
```

## 搜索论文

### 命令行搜索

```bash
arxiv search "machine learning" --max-results 5
arxiv search "transformer attention" --categories cs.CL --max-results 10
```

### Python API

```python
import arxiv

# 基础搜索
client = arxiv.Client()
search = arxiv.Search(
    query="LLM",
    max_results=5,
    sort_by=arxiv.SortCriterion.SubmittedDate
)

for paper in client.results(search):
    print(f"标题: {paper.title}")
    print(f"作者: {', '.join([a.name for a in paper.authors])}")
    print(f"日期: {paper.published}")
    print(f"PDF: {paper.pdf_url}")
    print(f"摘要: {paper.summary[:200]}...")
    print("---")

# 按分类搜索
search = arxiv.Search(
    query="cat:cs.CL",  # cs.CL = Computation and Language
    max_results=10,
    sort_by=arxiv.SortCriterion.Relevance
)
```

### 常用分类

- `cs.CL` - Computation and Language (NLP)
- `cs.CV` - Computer Vision
- `cs.LG` - Machine Learning
- `cs.AI` - Artificial Intelligence
- `stat.ML` - Machine Learning (Statistics)
- `math.OC` - Optimization and Control
- `physics.data-an` - Data Analysis

## 下载PDF

```python
import arxiv

# 下载PDF
client = arxiv.Client()
search = arxiv.Search(id_list=["2310.00001"])  # arXiv ID

for paper in client.results(search):
    paper.download_pdf(dirpath="~/Downloads", filename="paper.pdf")
    print(f"已下载: {paper.title}")
```

或直接用命令行：

```bash
arxiv download 2310.00001
```

## 获取论文信息

```python
import arxiv

paper = next(arxiv.Client().results(arxiv.Search(id_list=["2310.00001"])))

print(f"ID: {paper.entry_id}")
print(f"标题: {paper.title}")
print(f"作者: {[a.name for a in paper.authors]}")
print(f"摘要: {paper.summary}")
print(f"评论: {paper.comment}")
print(f"期刊: {paper.journal_ref}")
print(f"DOI: {paper.doi}")
print(f"分类: {paper.categories}")
print(f"PDF: {paper.pdf_url}")
```

## 高级搜索

```python
# 标题搜索
search = arxiv.Search(query="ti:transformer", max_results=5)

# 摘要搜索
search = arxiv.Search(query="abs:language model", max_results=5)

# 作者搜索
search = arxiv.Search(query="au:Ian Goodfellow", max_results=5)

# 组合搜索
search = arxiv.Search(
    query="(ti:machine AND ti:learning) AND (au:bishop OR au:pearl)",
    max_results=10
)
```

## 实用技巧

- arXiv ID 格式: `YYMM.NNNNN` (如 `2310.12345`)
- 早期论文: `cond-mat/0301001` (旧格式)
- 懒人用法: 直接用 Google 搜索 `arxiv:2310.12345` 可快速定位
