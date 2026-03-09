#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "arxiv>=2.0.0",
#     "pymupdf>=1.23.0",
# ]
# ///
"""
每天arXiv论文速览 - 单篇处理版
每篇论文单独调用一次LLM,完成后立即保存

Usage:
    python3 daily_arxiv.py [--force] [--categories cs.CL,cs.CV] [--max-results 3]

Environment Variables:
    MINIMAX_API_KEY: MiniMax API key

Configuration:
    Set in ~/.openclaw/openclaw.json under skills.arxiv

Output:
    - Markdown report: ~/arxiv-daily/YYYY-MM-DD.md
    - PDF cache: ~/arxiv-daily/pdfs/
    - JSON cache: ~/arxiv-daily/cache/
"""

import arxiv
import datetime
import os
import json
import time
import sys
from pathlib import Path
import fitz

# 配置
CATEGORIES = [
    ("cs.CL", "自然语言处理 (NLP)"),
    ("cs.CV", "计算机视觉 (CV)"),
    ("cs.LG", "机器学习 (ML)"),
    ("cs.AI", "人工智能 (AI)"),
    ("stat.ML", "统计机器学习 (Stat.ML)"),
]
MAX_RESULTS = 3
OUTPUT_DIR = Path("~/arxiv-daily").expanduser()
PDF_CACHE_DIR = OUTPUT_DIR / "pdfs"
CACHE_DIR = OUTPUT_DIR / "cache"

# Runtime configuration (set by argparse)
MODEL_NAME = "MiniMax-M2.5"
MAX_PDF_PAGES = 8
API_KEY_OVERRIDE = None

ANALYSIS_PROMPT = """你是一个专业的学术论文分析师。请仔细阅读以下论文内容，并按照以下结构生成详细的中文总结：

## 1. 论文要解决的问题
## 2. 现有方案的局限性
## 3. 思考Insight
## 4. 具体解决方案
## 5. 实验设计和结果
## 6.方案的局限性和未来展望

论文标题: {title}
论文作者: {authors}
论文摘要: {abstract}
论文正文内容:
{paper_content}

请严格按照上述6个结构输出。"""

def load_config():
    """Load configuration from OpenClaw config file"""
    config_path = Path("~/.openclaw/openclaw.json").expanduser()
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            return config.get("skills", {}).get("arxiv", {})
        except Exception:
            pass
    return {}

def get_api_key():
    """获取API Key (优先级: --api-key > 环境变量 > 配置文件 > auth-profiles)"""
    # 1. Command-line argument (highest priority)
    if API_KEY_OVERRIDE:
        return API_KEY_OVERRIDE

    # 2. Environment variable
    env_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if env_key:
        return env_key

    # 3. OpenClaw config file
    config = load_config()
    if "apiKey" in config:
        key = config["apiKey"].strip()
        if key:
            return key

    if "env" in config and "MINIMAX_API_KEY" in config["env"]:
        key = config["env"]["MINIMAX_API_KEY"].strip()
        if key:
            return key

    # 4. Auth profiles (fallback)
    config_path = Path("~/.openclaw/agents/main/agent/auth-profiles.json").expanduser()
    if config_path.exists():
        try:
            auth_config = json.loads(config_path.read_text())
            profiles = auth_config.get("profiles", {})
            if "minimax:default" in profiles:
                key = profiles["minimax:default"].get("key", "").strip()
                if key:
                    return key
            elif "minimax-portal:default" in profiles:
                key = profiles["minimax-portal:default"].get("access", "").strip()
                if key:
                    return key
        except Exception:
            pass

    return ""

def search_papers(category, max_results=10):
    client = arxiv.Client()
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending
    )
    return list(client.results(search))

def download_pdf(paper, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{paper.entry_id.split('/')[-1]}.pdf"
    filepath = output_dir / filename
    
    if filepath.exists():
        return filepath
    
    try:
        paper.download_pdf(dirpath=str(output_dir), filename=filename)
        return filepath
    except Exception as e:
        print(f"  下载失败: {e}", file=sys.stderr)
        return None

def extract_text_from_pdf(pdf_path, max_pages=None):
    if max_pages is None:
        max_pages = MAX_PDF_PAGES
    try:
        doc = fitz.open(pdf_path)
        text_parts = []
        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
        doc.close()
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"  PDF提取失败: {e}", file=sys.stderr)
        return None

def analyze_paper_with_llm(title, authors, abstract, paper_content):
    api_key = get_api_key()
    if not api_key:
        return None
    
    prompt = ANALYSIS_PROMPT.format(
        title=title,
        authors=authors,
        abstract=abstract,
        paper_content=paper_content[:8000]
    )
    
    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一个专业的学术论文分析师，擅长理解技术论文并用中文输出结构化总结。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                return None
    except Exception as e:
        print(f"  LLM调用失败: {e}", file=sys.stderr)
        return None

def process_single_paper(paper_info, pdf_dir, cache_file, index, results):
    """处理单篇论文，立即保存"""
    print(f"  [{index+1}] {paper_info['title'][:40]}...")
    
    # 下载PDF - 直接用ID构造arxiv对象
    from arxiv import Result
    class FakePaper:
        def __init__(self, entry_id, pdf_url):
            self.entry_id = entry_id
            self.pdf_url = pdf_url
    
    arxiv_id = paper_info['arxiv_id']
    fake_paper = FakePaper(f"http://arxiv.org/abs/{arxiv_id}", paper_info['pdf_url'])
    pdf_path = download_pdf(fake_paper, pdf_dir)
    
    paper_content = ""
    if pdf_path and pdf_path.exists():
        paper_content = extract_text_from_pdf(pdf_path)
        if paper_content:
            print(f"      提取文本 {len(paper_content)} 字符")
    
    # LLM分析
    if paper_content:
        analysis = analyze_paper_with_llm(
            paper_info['title'],
            ", ".join(paper_info['authors'][:5]),
            paper_info['abstract'],
            paper_content
        )
        paper_info['analysis'] = analysis
        if analysis:
            print(f"      LLM完成")
        time.sleep(1)
    
    # 立即保存
    results[index] = paper_info
    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"      已保存")

def process_category(cat_code, cat_name, force=False):
    """处理单个分类"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cat_code}.json"

    # 检查缓存
    if cache_file.exists() and not force:
        # 检查是否所有论文都有analysis
        try:
            cached = json.loads(cache_file.read_text(encoding='utf-8'))
            all_done = all(p.get('analysis') for p in cached)
            if all_done:
                print(f"  {cat_name} 已完成，跳过")
                return cache_file
        except:
            pass

    print(f"\n=== 处理 {cat_name} ===")
    papers = search_papers(cat_code, MAX_RESULTS)

    results = []
    for i, paper in enumerate(papers):
        paper_info = {
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "date": paper.published.strftime('%Y-%m-%d'),
            "arxiv_id": paper.entry_id.split('/')[-1],
            "pdf_url": paper.pdf_url,
            "abstract": paper.summary,
            "comment": paper.comment,
            "doi": paper.doi,
            "analysis": None
        }
        results.append(paper_info)
    
    # 初始保存
    cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # 逐篇处理
    for i, paper_info in enumerate(results):
        if not paper_info.get('analysis'):
            process_single_paper(paper_info, PDF_CACHE_DIR, cache_file, i, results)
    
    print(f"  {cat_name} 完成")
    return cache_file

def format_paper(paper_info):
    lines = []
    lines.append(f"### {paper_info['title']}")
    lines.append("")
    lines.append(f"- **作者**: {', '.join(paper_info['authors'][:5])}{'...' if len(paper_info['authors']) > 5 else ''}")
    lines.append(f"- **日期**: {paper_info['date']}")
    lines.append(f"- **arXiv**: [{paper_info['arxiv_id']}]({paper_info['pdf_url'].replace('abs', 'pdf')})")
    lines.append(f"- **PDF**: [下载]({paper_info['pdf_url']})")
    if paper_info.get('comment'):
        lines.append(f"- **评论**: {paper_info['comment']}")
    lines.append("")
    lines.append(f"**摘要**: {paper_info['abstract'][:300]}...")
    lines.append("")
    
    if paper_info.get('analysis'):
        lines.append("---")
        lines.append("")
        lines.append("## 📊 论文深度分析")
        lines.append("")
        lines.append(paper_info['analysis'])
        lines.append("")
    else:
        lines.append("*(无深度分析)*")
        lines.append("")
    
    return "\n".join(lines)

def generate_final_report():
    """生成最终报告"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    today = datetime.date.today()
    output_file = OUTPUT_DIR / f"{today}.md"
    
    lines = []
    lines.append(f"# arXiv 每日论文速览 (深度分析版)")
    lines.append("")
    lines.append(f"**日期**: {today}")
    lines.append(f"**更新时间**: {datetime.datetime.now().strftime('%H:%M:%S')}")
    lines.append("")
    lines.append("> 📝 每篇论文都经过LLM深度分析")
    lines.append("")
    
    total = 0
    for cat_code, cat_name in CATEGORIES:
        cache_file = process_category(cat_code, cat_name)
        
        if cache_file.exists():
            results = json.loads(cache_file.read_text(encoding='utf-8'))
            total += len(results)
            
            lines.append(f"## {cat_name}")
            lines.append("")
            
            for paper_info in results:
                lines.append(format_paper(paper_info))
            
            lines.append("")
    
    lines.append(f"---\n共 {total} 篇论文")
    
    content = "\n".join(lines)
    output_file.write_text(content, encoding="utf-8")
    print(f"\n✅ 已生成: {output_file}")
    return output_file

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="每天arXiv论文速览 - 使用LLM深度分析"
    )
    parser.add_argument("--force", action="store_true", help="强制重新处理所有论文")
    parser.add_argument("--categories", help="逗号分隔的分类列表")
    parser.add_argument("--max-results", type=int, help="每个分类的最大论文数")
    parser.add_argument("--model", help="LLM模型名称")
    parser.add_argument("--max-pages", type=int, help="PDF提取的最大页数")
    parser.add_argument("--api-key", help="MiniMax API key")
    parser.add_argument("--output-dir", help="输出目录")

    args = parser.parse_args()

    # Load config and merge with args
    config = load_config()

    # Update module-level config (priority: args > config > defaults)
    if args.categories:
        cat_list = [c.strip() for c in args.categories.split(",")]
        CATEGORIES = [(c, c) for c in cat_list]
    elif "categories" in config:
        CATEGORIES = [(c, c) for c in config["categories"]]

    MAX_RESULTS = args.max_results or config.get("maxResults", 3)
    MODEL_NAME = args.model or config.get("model", "MiniMax-M2.5")
    MAX_PDF_PAGES = args.max_pages or config.get("maxPages", 8)
    API_KEY_OVERRIDE = args.api_key

    if args.output_dir:
        OUTPUT_DIR = Path(args.output_dir).expanduser()
    elif "outputDir" in config:
        OUTPUT_DIR = Path(config["outputDir"]).expanduser()

    PDF_CACHE_DIR = OUTPUT_DIR / "pdfs"
    CACHE_DIR = OUTPUT_DIR / "cache"

    # Validate API key
    if not get_api_key():
        print("错误: 未找到API密钥", file=sys.stderr)
        print("请通过以下方式之一提供:", file=sys.stderr)
        print("  1. --api-key 参数", file=sys.stderr)
        print("  2. MINIMAX_API_KEY 环境变量", file=sys.stderr)
        print("  3. ~/.openclaw/openclaw.json 配置文件", file=sys.stderr)
        sys.exit(1)

    try:
        generate_final_report()
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
