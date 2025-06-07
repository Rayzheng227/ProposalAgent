"""
过程中涉及到的一些工具，工具相关配置见:tools.json
"""
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeoutError
import arxiv
from langchain_core.tools import tool
import logging
import os
from dotenv import load_dotenv
from typing import List, Dict 
from langchain_community.tools import TavilySearchResults
from crossref.restful import Works
from langchain_core.messages import HumanMessage, SystemMessage
import fitz
from langchain_openai import ChatOpenAI


load_dotenv()
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

@tool
def search_arxiv_papers_tool(query: str, max_results: int = 10, Download: bool = True) -> List[Dict]:
    """搜索并下载ArXiv论文的工具
    
    Args:
        query: 搜索关键词
        max_results: 最大结果数量，默认5篇
        Download: 是否下载PDF文件
    
    Returns:
        包含论文信息的字典列表
        以及存储在Papers目录下的参考文献
    """
    logging.info(f"在arxiv上搜索:{query}")
    
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        
        papers_dir = "./Papers"
        if not os.path.exists(papers_dir):
            os.makedirs(papers_dir)
        
        papers = []
        for paper in client.results(search):
            paper_info = {
                "title": paper.title,
                "authors": [author.name for author in paper.authors],
                "summary": paper.summary[:300] + "...",  # 截断摘要
                "published": paper.published.strftime("%Y-%m-%d"),
                "pdf_url": paper.pdf_url,
                "categories": paper.categories,
                "arxiv_id": paper.entry_id.split('/')[-1]
            }
            
            if Download:
                try:
                    # 下载PDF - 改进文件名处理和错误处理
                    logging.info(f"正在下载论文：{paper.title[:50]}...")
                    
                    # 更安全的文件名处理
                    import re
                    safe_title = re.sub(r'[^\w\s-]', '', paper.title)  # 移除特殊字符
                    safe_title = re.sub(r'[-\s]+', '-', safe_title)    # 替换空格和多个连字符
                    safe_title = safe_title.strip('-')[:40]             # 限制长度并移除首尾连字符
                    
                    if not safe_title:  # 如果标题处理后为空，使用默认名称
                        safe_title = "paper"
                    
                    filename = f"{paper_info['arxiv_id']}_{safe_title}.pdf"
                    full_path = os.path.join(papers_dir, filename)
                    
                    # 检查文件是否已存在
                    if os.path.exists(full_path):
                        logging.info(f"论文已存在，跳过下载: {filename}")
                        paper_info["local_pdf_path"] = full_path
                    else:
                        # 使用更稳定的下载方法
                        import time
                        time.sleep(5)  # 增加下载间隔时间，例如5秒，以减少服务器压力
                        
                        paper.download_pdf(dirpath=papers_dir, filename=filename)
                        
                        # 验证下载是否成功
                        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
                            paper_info["local_pdf_path"] = full_path
                            logging.info(f"✅ 成功下载: {filename}")
                        else:
                            paper_info["local_pdf_path"] = None
                            logging.warning(f"❌ 下载失败或文件为空: {filename}")
                        
                except Exception as e:
                    paper_info["local_pdf_path"] = None
                    logging.warning(f"❌ 下载论文失败: {paper.title[:50]}... - 错误: {str(e)}")
                    
                    # 如果下载失败，尝试记录更详细的错误信息
                    error_str = str(e).lower()
                    if "timeout" in error_str:
                        logging.warning("可能的网络超时问题。")
                    elif "permission" in error_str or "403" in error_str or "forbidden" in error_str:
                        logging.warning("可能的权限问题或请求被禁止 (403 Forbidden)。这可能是由于请求频率过高。")
                    elif "not found" in error_str or "404" in error_str:
                        logging.warning("PDF文件可能不存在 (404 Not Found)。")
                    elif "bad gateway" in error_str or "502" in error_str:
                        logging.warning("服务器端错误 (502 Bad Gateway)。这可能是ArXiv服务器的临时问题。")
            
            papers.append(paper_info)
            
            # 限制处理数量，避免过多请求
            if len(papers) >= max_results:
                break

        logging.info(f"✅ ArXiv搜索完成，共找到 {len(papers)} 篇论文")
        successful_downloads = len([p for p in papers if p.get("local_pdf_path")])
        logging.info(f"📄 成功下载 {successful_downloads} 个PDF文件")
        
        return papers

    except Exception as e:
        logging.error(f"❌ ArXiv搜索失败: {str(e)}")
        return [{"error": f"ArXiv搜索失败: {str(e)}"}]


@tool
def search_web_content_tool(query: str) -> List[Dict]:
    """使用Tavily搜索网络内容的工具
    
    Args:
        query: 搜索查询
        
    Returns:
        搜索结果列表
    """
    logging.info(f"正在网络搜索:{query}")
    
    try:
        os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY
        tavily_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=True
        )
        
        results = tavily_tool.invoke({"query": query})
        return results
    
    except Exception as e:
        return [{"error": f"网络搜索失败: {str(e)}"}]


@tool
def search_crossref_papers_tool(query: str, max_results: int = 5) -> List[Dict]:
    """使用 CrossRef 搜索论文元数据的工具

    Args:
        query: 关键词或主题
        max_results: 返回结果数量上限（默认5）

    Returns:
        包含论文信息的字典列表
    """
    logging.info(f"在crossref上搜索:{query}")
    
    try:
        works = Works()
        search = works.query(query).sort('relevance')

        results = []
        for i, item in enumerate(search):
            if i >= max_results:
                break

            paper_info = {
                "title": item.get("title", ["No title"])[0],
                "authors": [
                    f"{author.get('given', '')} {author.get('family', '')}".strip()
                    for author in item.get("author", [])
                ],
                "doi": item.get("DOI", "N/A"),
                "published": "-".join(str(d) for d in item.get("issued", {}).get("date-parts", [[None]])[0]),
                "publisher": item.get("publisher", "N/A"),
                "journal": item.get("container-title", ["N/A"])[0],
                "url": item.get("URL", "N/A")
            }

            results.append(paper_info)

        return results

    except Exception as e:
        return [{"error": f"CrossRef 搜索失败: {str(e)}"}]


@tool
def summarize_pdf(path: str, max_chars: int = 10000) -> Dict:
    """总结PDF文件内容的工具
    
    Args:
        path: PDF文件路径
        max_chars: 最大字符数限制，默认10000
        
    Returns:
        包含摘要和源文本片段的字典。如果摘要生成超时或失败，摘要内容将为空字符串。
    """
    logging.info(f"调用工具：summarize_pdf:{path}")
    
    full_text = ""
    source_excerpt = ""
    total_length = 0

    try:
        # 1. 打开并提取 PDF 文本
        doc = fitz.open(path)
        for page_num, page in enumerate(doc):
            full_text += page.get_text()
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars]
                logging.info(f"PDF '{path}' 内容已截断至 {max_chars} 字符。")
                break
        doc.close()

        source_excerpt = full_text[:500] + "..." if full_text else ""
        total_length = len(full_text)

        if not full_text.strip():
            logging.warning(f"PDF 文件 '{path}' 中未找到可用文本。")
            return {
                "summary": "", 
                "error": "PDF 文件中未找到可用文本", 
                "source_excerpt": source_excerpt, 
                "total_length": total_length
            }

        # 2. 构造摘要提示
        prompt = f"""
        You are an academic assistant specializing in research paper analysis.
        Summarize the following academic text into a comprehensive but concise analysis (around 300-400 words in Chinese).
        Focus on:
        1. 研究目标和问题
        2. 主要方法论
        3. 核心发现和结论
        4. 研究贡献和意义
        
        请用中文回答，使用学术化的语言。

        Text:
        \"\"\"
        {full_text}
        \"\"\"
        """

        # 3. 调用语言模型
        llm = ChatOpenAI(
            temperature=0, 
            model="qwen-plus", 
            base_url=base_url, 
            api_key=DASHSCOPE_API_KEY
        )

        logging.info(f"正在为PDF文件 '{path}' 生成摘要 (超时时间: 120秒)...")
        
        summary_content = "" # 默认为空值

        def llm_call():
            return llm.invoke([HumanMessage(content=prompt)])

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(llm_call)
            try:
                response = future.result(timeout=120)  # 2分钟超时
                summary_content = response.content.strip()
                logging.info(f"✅ PDF摘要生成成功: {path}")
            except FuturesTimeoutError:
                logging.warning(f"⏳ PDF摘要生成超时 (超过120秒): {path}. 返回空摘要。")
                summary_content = "" # 超时则摘要为空字符串
            except Exception as e_invoke:
                logging.error(f"❌ PDF摘要生成过程中LLM调用失败: {path} - {str(e_invoke)}")
                return {
                    "summary": "", 
                    "error": f"LLM调用失败: {str(e_invoke)}",
                    "source_excerpt": source_excerpt,
                    "total_length": total_length
                }
        
        return {
            "summary": summary_content,
            "source_excerpt": source_excerpt,
            "total_length": total_length
        }

    except Exception as e:
        logging.error(f"❌ PDF摘要工具执行失败: {path} - {str(e)}")
        return {
            "summary": "", 
            "error": f"PDF摘要失败: {str(e)}",
            "source_excerpt": source_excerpt, # 即使出错，也尝试返回已提取的部分
            "total_length": total_length
        }