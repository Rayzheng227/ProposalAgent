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
import backend.src.agent.rag as rag
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

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
    logging.info(f"在arxiv上搜索领域为:{query}")

    try:
        content = rag.generate_search_queries(query)
        queries = [line.strip() for line in content.split('\n') if line.strip()]
        logging.info(f"在arxiv上搜索关键词为:{queries}")
        papers = []
        seen_ids = set()
        
        # 添加SSL和连接配置
        import ssl
        import urllib3
        
        # 禁用SSL警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        for q in queries:
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    # 创建客户端时添加延迟和重试机制
                    client = arxiv.Client(
                        page_size=min(10, max(2, max_results // len(queries))),
                        delay_seconds=3,  # 增加延迟
                        num_retries=2
                    )
                    
                    search = arxiv.Search(
                        query=q,
                        max_results=max(2, max_results // len(queries)),
                        sort_by=arxiv.SortCriterion.SubmittedDate
                    )

                    papers_dir = "./Papers"
                    if not os.path.exists(papers_dir):
                        os.makedirs(papers_dir)

                    # 添加超时控制
                    import time
                    search_start_time = time.time()
                    timeout_seconds = 30  # 30秒超时
                    
                    for paper in client.results(search):
                        # 检查超时
                        if time.time() - search_start_time > timeout_seconds:
                            logging.warning(f"ArXiv搜索超时，停止当前查询: {q}")
                            break
                            
                        if paper.entry_id in seen_ids:
                            continue
                            
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

                        seen_ids.add(paper.entry_id)
                        papers.append(paper_info)

                        # 限制处理数量，避免过多请求
                        if len(papers) >= max_results:
                            break
                    
                    # 如果成功，跳出重试循环
                    break
                    
                except Exception as search_error:
                    retry_count += 1
                    error_str = str(search_error).lower()
                    
                    if retry_count < max_retries:
                        wait_time = retry_count * 5  # 递增等待时间
                        logging.warning(f"ArXiv搜索失败 (尝试 {retry_count}/{max_retries}): {str(search_error)}")
                        logging.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"ArXiv搜索最终失败: {str(search_error)}")
                        
                        # 提供详细的错误诊断
                        if "ssl" in error_str or "eof" in error_str:
                            logging.error("SSL连接错误，可能是网络问题或ArXiv服务器问题")
                        elif "timeout" in error_str:
                            logging.error("连接超时，请检查网络连接")
                        elif "max retries" in error_str:
                            logging.error("达到最大重试次数，ArXiv服务可能暂时不可用")

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
    logging.info(f"正在网络搜索领域:{query}")
    queries = rag.generate_search_queries(query)
    logging.info(f"正在网络搜索关键词:{queries}")

    try:
        os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY
        tavily_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=True
        )

        results = tavily_tool.invoke({"query": queries})
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
    logging.info(f"在crossref上搜索领域:{query}")
    queries = rag.generate_search_queries(query)
    logging.info(f"在crossref上搜索领域:{queries}")

    try:
        works = Works()
        search = works.query(queries).sort('relevance')

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


@tool
def generate_gantt_chart_tool(timeline_content: str, research_field: str = "") -> Dict:
    """生成项目甘特图的工具
    
    Args:
        timeline_content: 包含时间规划的文本内容
        research_field: 研究领域名称，用于图表标题
        
    Returns:
        包含Mermaid甘特图代码的字典
    """
    logging.info(f"调用工具：generate_gantt_chart_tool")
    logging.info(f"输入研究领域: {research_field}")
    logging.info(f"输入时间线内容长度: {len(timeline_content)} 字符")
    logging.info(f"时间线内容前200字符: {timeline_content[:200]}...")
    
    try:
        # 构造甘特图生成提示
        gantt_prompt = f"""
        你是一个项目管理专家，需要根据提供的研究时间线内容生成Mermaid格式的甘特图。

        **研究领域：** {research_field}
        
        **时间线内容：**
        {timeline_content}
        
        **要求：**
        1. 仔细分析时间线内容，提取关键的阶段、任务和时间节点
        2. 将任务按逻辑分组为不同的section（如：文献调研、系统设计、实验评估等）
        3. 生成标准的Mermaid甘特图语法
        4. 使用合理的日期格式（YYYY-MM-DD）
        5. 根据任务的重要性和依赖关系设置状态（done, active, 或不设置）
        6. 确保时间安排合理，避免任务重叠冲突
        
        **输出格式要求：**
        只输出纯净的Mermaid代码，格式如下：
        ```mermaid
        gantt
            dateFormat  YYYY-MM-DD
            title       [研究项目标题]
            section [阶段名称1]
            [任务名称1]    :done,   YYYY-MM-DD, YYYY-MM-DD
            [任务名称2]    :active, YYYY-MM-DD, 30d
            section [阶段名称2]
            [任务名称3]    :        YYYY-MM-DD, 20d
            [任务名称4]    :        YYYY-MM-DD, 25d
        ```
        
        注意：
        - 不要包含任何解释文字，只输出Mermaid代码
        - 确保语法正确，可以直接渲染
        - 如果时间线内容不够详细，请基于常见的研究项目流程进行合理推断
        - 必须以"gantt"开头
        """

        # 调用LLM生成甘特图
        llm = ChatOpenAI(
            temperature=0,
            model="qwen-plus",
            base_url=base_url,
            api_key=DASHSCOPE_API_KEY
        )

        logging.info(f"正在调用LLM生成甘特图...")
        
        response = llm.invoke([HumanMessage(content=gantt_prompt)])
        gantt_content = response.content.strip()
        
        logging.info(f"LLM原始响应长度: {len(gantt_content)} 字符")
        logging.info(f"LLM原始响应前500字符: {gantt_content[:500]}...")
        
        # 清理输出，确保只包含Mermaid代码
        if "```mermaid" in gantt_content:
            start = gantt_content.find("```mermaid") + 10
            end = gantt_content.find("```", start)
            if end != -1:
                gantt_content = gantt_content[start:end].strip()
                logging.info("✅ 成功提取mermaid代码块")
        elif "```" in gantt_content:
            start = gantt_content.find("```") + 3
            end = gantt_content.find("```", start)
            if end != -1:
                gantt_content = gantt_content[start:end].strip()
                logging.info("✅ 成功提取通用代码块")
        else:
            logging.info("⚠️ 未找到代码块标记，使用原始内容")
        
        # 验证甘特图内容
        if not gantt_content.startswith("gantt"):
            if gantt_content.strip():
                gantt_content = "gantt\n" + gantt_content
                logging.info("⚠️ 添加了缺失的'gantt'开头")
            else:
                logging.error("❌ 甘特图内容为空")
                return {
                    "gantt_chart": "",
                    "status": "error",
                    "message": "生成的甘特图内容为空"
                }
        
        logging.info(f"✅ 最终甘特图内容长度: {len(gantt_content)} 字符")
        logging.info(f"最终甘特图内容前300字符: {gantt_content[:300]}...")
        
        return {
            "gantt_chart": gantt_content,
            "status": "success",
            "message": "甘特图生成成功"
        }
        
    except Exception as e:
        logging.error(f"❌ 甘特图生成失败: {str(e)}")
        import traceback
        logging.error(f"详细错误信息: {traceback.format_exc()}")
        return {
            "gantt_chart": "",
            "status": "error", 
            "message": f"甘特图生成失败: {str(e)}"
        }