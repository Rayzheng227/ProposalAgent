import arxiv
from langchain_community.tools import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, List, Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import json
import os
from datetime import datetime
import logging

"""
API的配置——[TODO]同步到网上前记得修改！
"""
base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_API_KEY = "sk-eafdf8e1d0fb4717a883c87788e76182"

Tavily_API_KEY = "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"


class ProposalState(TypedDict):
    """定义Proposal生成过程中的状态"""
    research_field: str
    query: str
    arxiv_papers: List[Dict]
    web_search_results: List[Dict]
    background: str
    objectives: str
    methodology: str
    timeline: str
    expected_outcomes: str
    final_proposal: str
    messages: List[Any]
    research_plan: str



@tool
def search_arxiv_papers_tool(query: str, max_results: int = 5) -> List[Dict]:
    """搜索并下载ArXiv论文的工具
    
    Args:
        query: 搜索关键词
        max_results: 最大结果数量，默认5篇
    
    Returns:
        包含论文信息的字典列表
    """
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
            
            try:
                # 下载PDF
                safe_title = "".join(c for c in paper.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                safe_title = safe_title[:50]
                filename = f"{paper_info['arxiv_id']}_{safe_title}.pdf"
                
                paper.download_pdf(dirpath=papers_dir, filename=filename)
                paper_info["local_pdf_path"] = os.path.join(papers_dir, filename)
                
            except Exception as e:
                paper_info["local_pdf_path"] = None
                
            papers.append(paper_info)
        
        return papers
    
    except Exception as e:
        return [{"error": f"ArXiv搜索失败: {str(e)}"}]
    

# 定义网络搜索工具
@tool
def search_web_content_tool(query: str) -> List[Dict]:
    """使用Tavily搜索网络内容的工具
    
    Args:
        query: 搜索查询
        
    Returns:
        搜索结果列表
    """
    try:
        os.environ["TAVILY_API_KEY"] = Tavily_API_KEY
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
    

class ProposalAgent:
    def __init__(self):
        """初始化ProposalAgent"""
        self.llm = ChatOpenAI(
            api_key= DASHSCOPE_API_KEY,
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0
        )
        
        # 设置Tavily API密钥
        os.environ["TAVILY_API_KEY"] = Tavily_API_KEY

        # 初始化工具
        self.arxiv_client = arxiv.Client()
        self.tavily_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=True
        )
        
        self.papers_dir = "./Papers"
        if not os.path.exists(self.papers_dir):
            os.makedirs(self.papers_dir)
        # 构建工作流图
        self.workflow = self._build_workflow()
    
    def search_arxiv_papers(self, query: str, max_results: int = 10) -> List[Dict]:
        """搜索并下载ArXiv论文"""
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        

        papers = []
        for paper in self.arxiv_client.results(search):
            paper_info = {
                "title": paper.title,
                "authors": [author.name for author in paper.authors],
                "summary": paper.summary,
                "published": paper.published.strftime("%Y-%m-%d"),
                "pdf_url": paper.pdf_url,
                "categories": paper.categories,
                "arxiv_id": paper.entry_id.split('/')[-1]  # 提取arxiv ID
            }
            try:
                # 创建安全的文件名（去除特殊字符）
                safe_title = "".join(c for c in paper.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                safe_title = safe_title[:50]  # 限制文件名长度
                filename = f"{paper_info['arxiv_id']}_{safe_title}.pdf"
                
                paper.download_pdf(dirpath=self.papers_dir, filename=filename)
                paper_info["local_pdf_path"] = os.path.join(self.papers_dir, filename)
                logging.info(f"已下载论文: {paper.title}")

            except Exception as e:
                logging.error(f"下载论文失败 {paper.title}: {e}")
                paper_info["local_pdf_path"] = None
            
            papers.append(paper_info)

        return papers
    
    def search_web_content(self, query: str) -> List[Dict]:
        """使用Tavily搜索网络内容"""
        try:
            results = self.tavily_tool.invoke({"query": query})
            return results
        except Exception as e:
            logging.error(f"Web search error: {e}")
            return []

    def create_master_plan_node(self, state: ProposalState) -> ProposalState:
        """首先基于问题去创建一个总体研究计划(不同于Proposal)"""
        research_field = state["research_field"]

        master_planning_prompt = f"""
        你是一个资深的科研专家和项目规划师。用户提出了一个研究问题或领域："{research_field}"

        请你制定一个全面的研究计划，这个计划应该包括：

        1. **问题理解与分析**
        - 对研究问题的深入理解
        - 问题的重要性和研究价值
        - 预期的研究难点和挑战

        2. **文献调研计划**
        - 需要检索哪些关键词
        - 重点关注哪些研究方向
        - 需要查找哪些类型的文献（理论、实验、综述等）
        - 文献检索的优先级

        3. **研究目标设定**
        - 总体研究目标
        - 分解的子目标
        - 各目标的优先级

        4. **技术路线规划**
        - 采用什么研究方法
        - 技术实现思路
        - 实验设计方案

        5. **工作安排**
        - 各阶段的工作内容
        - 时间分配
        - 里程碑设定

        6. **预期成果**
        - 期望达到的目标
        - 可交付的成果

        请基于"{research_field}"这个研究问题，制定一个详细、可行的研究计划。
        计划要具有指导性，后续的所有工作都将基于这个计划来执行。
        """
        logging.info(f"🤖 Agent正在为 '{research_field}' 制定总体研究计划...")
        response = self.llm.invoke([HumanMessage(content=master_planning_prompt)])
        
        state["research_plan"] = response.content
        logging.info("✅ 总体研究计划制定完成")

        return state
    
    def literature_research_node(self, state: ProposalState) -> ProposalState:
        """基于研究计划进行文献检索"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        
        # 首先让Agent分析计划，确定检索策略
        search_strategy_prompt = f"""
        基于以下研究计划，确定文献检索的关键词和策略：

        研究计划：
        {research_plan}

        请分析并提取：
        1. 主要检索关键词（3-5个）
        2. 次要检索关键词（2-3个）
        3. 检索的重点方向

        只返回关键词列表，用逗号分隔，不要其他解释。
        格式：主要关键词1,主要关键词2,次要关键词1,次要关键词2
        """
        
        print("🔍 基于研究计划确定检索策略...")
        strategy_response = self.llm.invoke([HumanMessage(content=search_strategy_prompt)])
        keywords = strategy_response.content.strip()
        
        print(f"📚 开始检索文献，关键词：{keywords}")
        
        # 使用提取的关键词进行检索
        search_queries = [research_field] + [kw.strip() for kw in keywords.split(',')][:3]
        
        all_papers = []
        for query in search_queries:
            papers = self.search_arxiv_papers(query, max_results=5)
            all_papers.extend(papers)
        
        # 去重（基于title）
        seen_titles = set()
        unique_papers = []
        for paper in all_papers:
            if paper['title'] not in seen_titles:
                seen_titles.add(paper['title'])
                unique_papers.append(paper)
        
        # 搜索网络内容
        web_results = self.search_web_content(f"{research_field} research recent developments")
        
        state["arxiv_papers"] = unique_papers[:10]  # 限制数量
        state["web_search_results"] = web_results
        state["query"] = research_field
        
        print(f"📖 文献检索完成，共找到 {len(unique_papers)} 篇论文")
        
        return state
    
    def _build_workflow(self) -> StateGraph:
        """构建工作流图"""
        workflow = StateGraph(ProposalState)
        
        # 添加节点
        workflow.add_node("create_master_plan", self.create_master_plan_node)      # 第一步：制定计划
        workflow.add_node("literature_research", self.literature_research_node)   # 第二步：基于计划检索文献
        # 后续可以添加其他节点...
        
        # 定义流程
        workflow.set_entry_point("create_master_plan")                           # 从制定计划开始
        workflow.add_edge("create_master_plan", "literature_research")           # 计划 → 文献检索
        workflow.add_edge("literature_research", END)                            # 暂时结束，后续可以添加更多节点
        
        return workflow.compile()
    