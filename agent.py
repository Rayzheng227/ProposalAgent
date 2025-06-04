import arxiv
from langchain_community.tools import TavilySearchResults
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, List, Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import json
import os
from datetime import datetime
import logging
from prompts import *

"""
API的配置——[TODO]同步到网上前记得修改！
"""
base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_API_KEY = "sk-eafdf8e1d0fb4717a883c87788e76182"

Tavily_API_KEY = "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"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ]
)

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
    available_tools: List[Dict]  # 存储可用工具信息
    execution_plan: List[Dict]  # 可执行的计划
    execution_memory: List[Dict]  # 已经执行的记忆
    current_step: int  # 当前执行的步骤
    max_iterations: int  # 最大迭代次数
    introduction: str
    literature_review: str
    research_design: str
    timeline_plan: str
    expected_results: str
    reference_list: List[Dict]  # 统一的参考文献列表
    ref_counter: int  # 参考文献计数器
    final_references: str  # 最终的参考文献部分




@tool
def search_arxiv_papers_tool(query: str, max_results: int = 5, Download = True) -> List[Dict]:
    """搜索并下载ArXiv论文的工具
    
    Args:
        query: 搜索关键词
        max_results: 最大结果数量，默认5篇
    
    Returns:
        包含论文信息的字典列表
        以及存储在Papers目录下的参考文献
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
            if Download:
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

        self.tools = [search_arxiv_papers_tool, search_web_content_tool]
        self.tools_description = self.load_tools_description()
        self.agent_with_tools = create_react_agent(self.llm, self.tools)
        self.workflow = self._build_workflow()

    
    def load_tools_description(self) -> List[Dict]:
        """从JSON文件加载工具描述"""
        try:
            with open('tools.json', 'r', encoding='utf-8') as f:
                tools_description = json.load(f)
            return tools_description
        except FileNotFoundError:
            print("警告: tools.json 文件未找到，使用默认工具描述")
            return []
        except json.JSONDecodeError:
            print("警告: tools.json 文件格式错误，使用默认工具描述")
            return []
        

    def get_tools_info_text(self) -> str:
        """将工具信息转换为文本描述"""
        if not self.tools_description:
            return "暂无可用工具信息"
        
        tools_text = "可用工具列表:\n\n"
        for tool_info in self.tools_description:
            func_info = tool_info.get("function", {})
            name = func_info.get("name", "未知工具")
            description = func_info.get("description", "无描述")
            
            tools_text += f"🔧 **{name}**\n"
            tools_text += f"   描述: {description}\n"
            
            # 添加参数信息
            params = func_info.get("parameters", {}).get("properties", {})
            if params:
                tools_text += f"   参数:\n"
                for param_name, param_info in params.items():
                    param_desc = param_info.get("description", "无描述")
                    param_type = param_info.get("type", "未知类型")
                    required = param_name in func_info.get("parameters", {}).get("required", [])
                    required_text = "必需" if required else "可选"
                    tools_text += f"     - {param_name} ({param_type}, {required_text}): {param_desc}\n"
            
            tools_text += "\n"
        
        return tools_text
    

    def create_master_plan_node(self, state: ProposalState) -> ProposalState:
        """首先基于问题去创建一个总体的规划(不同于Proposal)"""
        research_field = state["research_field"]

        tools_info = self.get_tools_info_text()

        master_planning_prompt = master_plan_instruction.format(
            research_field=research_field,
            tools_info=tools_info
        )
        logging.info(f"🤖 Agent正在为 '{research_field}' 制定总体研究计划...")
        response = self.llm.invoke([HumanMessage(content=master_planning_prompt)])
        
        state["research_plan"] = response.content
        state["available_tools"] = self.tools_description
        state["execution_memory"] = []
        state["current_step"] = 0
        state["max_iterations"] = 10

        logging.info("✅ 总体研究计划制定完成")
        logging.info(f"研究计划内容: {state['research_plan']}...")

        return state
    


    def plan_analysis_node(self, state: ProposalState) -> ProposalState:
        """解析研究计划,生成可执行步骤"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        tools_info = self.get_tools_info_text()
        execution_memory = state.get("execution_memory", [])


        memory_text = ""
        if execution_memory:
            memory_text = "\n\n执行历史:\n"
            for step in execution_memory:
                description = step.get('description', '未知步骤')
                result = step.get('result', '无结果')
                success = step.get('success', False)
                status = "成功" if success else "失败"
                memory_text += f"- {description}: {status} - {result[:100]}...\n"

        
        # 首先让Agent分析计划，确定检索策略
        plan_analysis_prompt = EXECUTION_PLAN_PROMPT.format(
            research_field=research_field,
            research_plan=research_plan,
            tools_info=tools_info,
            memory_text=memory_text
        )
        logging.info("🔍 Agent正在分析计划并生成执行步骤...")
        response = self.llm.invoke([HumanMessage(content=plan_analysis_prompt)])
        logging.info("生成计划", response.content)
        try:
            # 解析JSON响应
            response_text = response.content.strip()
           # 如果响应包含```json，则提取JSON部分
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                if end != -1:
                    response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                if end != -1:
                    response_text = response_text[start:end].strip()
            
            plan_data = json.loads(response_text)
            state["execution_plan"] = plan_data.get("steps", [])
        except json.JSONDecodeError:
            logging.error("无法解析执行计划JSON，使用默认计划")
            logging.error(f"原始响应: {response.content[:500]}...")
            # 默认执行计划
            state["execution_plan"] = [
                {
                    "step_id": 1,
                    "action": "search_arxiv_papers",
                    "parameters": {"query": research_field, "max_results": 5},
                    "description": f"搜索ArXiv上关于{research_field}的论文",
                    "expected_outcome": "找到相关的学术论文"
                }
            ]
        
        logging.info(f"✅ 生成了 {len(state['execution_plan'])} 个执行步骤")

        return state
    

    def execute_step_node(self, state: ProposalState) -> ProposalState:
        """执行当前步骤"""
        execution_plan = state.get("execution_plan", [])
        current_step = state.get("current_step", 0)
        execution_memory = state.get("execution_memory", [])
        
        if current_step >= len(execution_plan):
            logging.info("所有步骤已执行完成")
            return state
        
        current_action = execution_plan[current_step]
        action_name = current_action.get("action")
        parameters = current_action.get("parameters", {})
        description = current_action.get("description", "")
        
        logging.info(f"🚀 执行步骤 {current_step + 1}: {description}")
        
        # 执行对应的工具
        result = None
        try:
            if action_name == "search_arxiv_papers":
                result = search_arxiv_papers_tool.invoke(parameters)
                # 将结果保存到状态中
                if isinstance(result, list) and len(result) > 0:
                    state["arxiv_papers"].extend(result)
                    
            elif action_name == "search_web_content":
                result = search_web_content_tool.invoke(parameters)
                # 将结果保存到状态中
                if isinstance(result, list) and len(result) > 0:
                    state["web_search_results"].extend(result)
            
            # 每次收集到新数据后，立即更新参考文献列表
            state = self.add_references_from_data(state)
            
            # 记录执行结果
            execution_memory.append({
                "step_id": current_step + 1,
                "action": f"{action_name}({parameters})",
                "description": description,
                "result": str(result)[:200] if result else "无结果",
                "success": result is not None and (not isinstance(result, list) or len(result) > 0)
            })
            
        except Exception as e:
            logging.error(f"执行步骤失败: {e}")
            execution_memory.append({
                "step_id": current_step + 1,
                "action": f"{action_name}({parameters})",
                "description": description,
                "result": f"执行失败: {str(e)}",
                "success": False
            })
        
        state["execution_memory"] = execution_memory
        state["current_step"] = current_step + 1
        
        return state
    
    def add_references_from_data(self, state: ProposalState) -> ProposalState:
        """从收集的数据中提取并添加参考文献"""
        arxiv_papers = state.get("arxiv_papers", [])
        web_results = state.get("web_search_results", [])
        reference_list = state.get("reference_list", [])
        ref_counter = state.get("ref_counter", 1)
        
        # 处理ArXiv论文
        for paper in arxiv_papers:
            if "error" not in paper:
                # 检查是否已经存在
                paper_title = paper.get('title', 'Unknown')
                existing_ref = next((ref for ref in reference_list if ref.get('title') == paper_title), None)
                
                if not existing_ref:
                    reference_list.append({
                        "id": ref_counter,
                        "type": "ArXiv",
                        "title": paper_title,
                        "authors": paper.get('authors', []),
                        "published": paper.get('published', 'Unknown'),
                        "arxiv_id": paper.get('arxiv_id', ''),
                        "categories": paper.get('categories', []),
                        "summary": paper.get('summary', '')
                    })
                    ref_counter += 1
        
        # 处理网络搜索结果
        for result in web_results:
            if "error" not in result:
                result_title = result.get('title', result.get('url', 'Unknown'))
                existing_ref = next((ref for ref in reference_list if ref.get('title') == result_title), None)
                
                if not existing_ref:
                    reference_list.append({
                        "id": ref_counter,
                        "type": "Web",
                        "title": result_title,
                        "url": result.get('url', ''),
                        "content_preview": result.get('content', result.get('snippet', 'No content'))[:200]
                    })
                    ref_counter += 1
        
        state["reference_list"] = reference_list
        state["ref_counter"] = ref_counter
        
        return state
    
    def get_literature_summary_with_refs(self, state: ProposalState) -> str:
        """获取带有统一编号的文献摘要"""
        reference_list = state.get("reference_list", [])
        
        literature_summary = ""
        
        # 按类型分组显示
        arxiv_refs = [ref for ref in reference_list if ref.get("type") == "ArXiv"]
        web_refs = [ref for ref in reference_list if ref.get("type") == "Web"]
        
        if arxiv_refs:
            literature_summary += "\n\n**相关ArXiv论文：**\n"
            for ref in arxiv_refs:
                literature_summary += f"[{ref['id']}] {ref['title']}\n"
                literature_summary += f"   作者: {', '.join(ref['authors'])}\n"
                literature_summary += f"   发表时间: {ref['published']}\n"
                literature_summary += f"   摘要: {ref['summary']}\n"
                literature_summary += f"   分类: {', '.join(ref['categories'])}\n\n"
        
        if web_refs:
            literature_summary += "\n**相关网络信息：**\n"
            for ref in web_refs:
                literature_summary += f"[{ref['id']}] {ref['title']}\n"
                literature_summary += f"   来源: {ref['url']}\n"
                literature_summary += f"   内容摘要: {ref['content_preview']}...\n\n"
        
        return literature_summary
    
    def generate_reference_section(self, state: ProposalState) -> str:
        """生成格式化的参考文献部分"""
        reference_list = state.get("reference_list", [])
        
        if not reference_list:
            return ""
        
        ref_text = "\n\n## 参考文献\n\n"
        
        for ref in reference_list:
            if ref["type"] == "ArXiv":
                # ArXiv论文格式
                authors_str = ", ".join(ref["authors"]) if ref["authors"] else "未知作者"
                categories_str = ", ".join(ref["categories"]) if ref["categories"] else ""
                ref_text += f"[{ref['id']}] {authors_str}. {ref['title']}. arXiv:{ref['arxiv_id']} ({ref['published']})"
                if categories_str:
                    ref_text += f". Categories: {categories_str}"
                ref_text += "\n\n"
            elif ref["type"] == "Web":
                # 网络资源格式
                ref_text += f"[{ref['id']}] {ref['title']}. 访问时间: {datetime.now().strftime('%Y-%m-%d')}. URL: {ref['url']}\n\n"
        
        return ref_text

    def write_introduction_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的引言部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        
        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state)
        
        citation_instruction = """
        **引用要求：**
        1. 当提及相关研究或观点时，必须在句末添加引用标记，格式为 [编号]
        2. 引用标记对应上述文献列表中的编号
        3. 例如：人工智能在医疗诊断中显示出巨大潜力[1]，特别是在影像识别领域[2]。
        4. 不要编造不存在的引用，只能引用上述提供的文献
        5. 如果某个观点来自多个文献，可以使用 [1,2] 的格式
        """
        
        # 使用prompts.py中的instruction
        introduction_prompt = f"""
        {proposal_introduction_instruction}
        
        **研究主题：** {research_field}
        
        **研究计划：**
        {research_plan}
        
        **已收集的文献和信息：**
        {literature_summary}
        {citation_instruction}

        请基于以上信息，按照instruction的要求，为"{research_field}"这个研究主题撰写一个学术规范的引言部分。
        
        要求：
        1. 必须使用中文撰写
        2. 至少600字
        3. 结构清晰，包含研究主题介绍、重要性说明、研究空白到研究问题的推导
        4. 适当引用已收集的文献，使用上述编号系统
        5. 语言学术化，适合研究计划书
        6. **不要在引言部分包含参考文献列表**，只在正文中使用引用标记
        """
        
        logging.info("📝 正在生成研究计划书引言部分...")
        response = self.llm.invoke([HumanMessage(content=introduction_prompt)])
        
        # 只保存引言正文，不包含参考文献
        state["introduction"] = response.content
        logging.info("✅ 引言部分生成完成")
        
        return state

    def write_literature_review_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的文献综述部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        introduction_content = state.get("introduction", "")
        
        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state)
        
        # 生成引用指导
        citation_instruction = """
        **引用要求：**
        1. 当提及相关研究、理论或观点时，必须在句末添加引用标记，格式为 [编号]
        2. 引用标记对应上述文献列表中的编号
        3. 例如：深度学习在图像识别领域取得了显著进展[1,2]，但在可解释性方面仍存在挑战[3]。
        4. 不要编造不存在的引用，只能引用上述提供的文献
        5. 如果某个观点来自多个文献，可以使用 [1,2,3] 的格式
        6. 在论述不同观点或研究发现时，要明确标注来源
        7. 对于重要的理论框架或方法论，必须引用相关文献
        """

        # 连贯性指导
        coherence_instruction = """
        **与引言部分的连贯性要求：**
        1. 仔细阅读已完成的引言部分，理解其中提出的研究问题和识别的研究空白
        2. 文献综述应该深化和拓展引言中简要提及的研究领域
        3. 避免重复引言中已经详细阐述的背景信息
        4. 使用承接性语言，如"基于前述研究问题"、"针对引言中提出的..."等
        5. 确保文献综述的结论自然过渡到对拟议研究的必要性论证
        6. 对引言中提及的关键概念和理论进行更深入的文献分析
        """
        
        # 使用prompts.py中的LITERATURE_REVIEW_PROMPT
        literature_review_prompt = f"""
        {LITERATURE_REVIEW_PROMPT.format(research_field=research_field)}
        
        **研究主题：** {research_field}
        
        **研究计划：**
        {research_plan}
        
        **已完成的引言部分：**
        {introduction_content}
        
        **已收集的文献和信息：**
        {literature_summary}
        
        {citation_instruction}
        
        {coherence_instruction}
        
        请基于以上信息，按照instruction的要求，为"{research_field}"这个研究主题撰写一个学术规范的文献综述部分。
        
        要求：
        1. 必须使用中文撰写
        2. 至少800字
        3. 结构清晰，按主题组织文献，不要逐篇论文介绍
        4. 重点关注研究趋势、主要观点、研究方法和存在的争议
        5. 识别研究空白和不足，为后续研究提供依据
        6. 必须包含适当的文献引用，使用上述编号系统
        7. 语言学术化，适合研究计划书
        8. 避免简单罗列，要进行分析和综合
        9. **与引言部分保持连贯性**，避免重复内容，深化引言中的研究问题
        10. 使用承接性语言连接引言部分的内容
        """
        
        logging.info("📚 正在生成研究计划书文献综述部分...")
        response = self.llm.invoke([HumanMessage(content=literature_review_prompt)])
        
        # 注意：文献综述不重复添加参考文献部分，因为引言已经包含了完整的参考文献列表
        state["literature_review"] = response.content
        logging.info("✅ 文献综述部分生成完成")
        
        return state

    def write_research_design_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的研究设计部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        introduction_content = state.get("introduction", "")
        literature_review_content = state.get("literature_review", "")
        
        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state)
        
        # 生成引用指导
        citation_instruction = """
        **引用要求：**
        1. 当提及相关研究方法、理论框架或技术时，必须在句末添加引用标记，格式为 [编号]
        2. 引用标记对应文献列表中的编号
        3. 例如：本研究将采用混合方法研究设计[5]，结合定量分析和定性访谈[8,12]。
        4. 不要编造不存在的引用，只能引用已提供的文献
        5. 在描述方法论依据时要明确标注来源
        6. 对于重要的分析工具和技术框架，必须引用相关文献
        """

        # 连贯性指导
        coherence_instruction = """
        **与前文的连贯性要求：**
        1. 仔细分析引言部分提出的具体研究问题，确保研究设计能够回答这些问题
        2. 基于文献综述中识别的方法论趋势和研究空白，选择合适的研究方法
        3. 承接文献综述中提到的理论框架和分析方法，说明如何在本研究中应用或改进
        4. 使用承接性语言，如"基于前述文献分析"、"针对引言中提出的研究问题"、"借鉴文献综述中的..."等
        5. 确保研究设计的每个组成部分都与前文建立的研究背景和理论基础相呼应
        6. 明确说明为什么选择的方法适合解决引言中提出的研究问题
        """
        
        # 使用prompts.py中的PROJECT_DESIGN_PROMPT
        research_design_prompt = f"""
        {PROJECT_DESIGN_PROMPT.format(research_field=research_field)}
        
        **研究主题：** {research_field}
        
        **研究计划：**
        {research_plan}
        
        **已完成的引言部分：**
        {introduction_content}
        
        **已完成的文献综述部分：**
        {literature_review_content}
        
        **已收集的文献和信息：**
        {literature_summary}
        
        {citation_instruction}
        
        {coherence_instruction}
        
        请基于以上信息，按照instruction的要求，为"{research_field}"这个研究主题撰写一个学术规范的研究设计部分。
        
        要求：
        1. 必须使用中文撰写
        2. 至少800字
        3. 结构清晰，包含数据来源、研究方法、分析策略、工作流程等
        4. 明确回应引言中提出的研究问题
        5. 基于文献综述中的方法论分析，选择合适的研究方法
        6. 必须包含适当的文献引用，使用统一编号系统
        7. 语言学术化，适合研究计划书
        8. **与引言和文献综述保持逻辑连贯性**
        9. 使用承接性语言连接前文内容
        10. 说明研究设计的可行性和局限性
        """
        
        logging.info("🔬 正在生成研究计划书研究设计部分...")
        response = self.llm.invoke([HumanMessage(content=research_design_prompt)])
        
        state["research_design"] = response.content
        logging.info("✅ 研究设计部分生成完成")
        
        return state

    def generate_final_references_node(self, state: ProposalState) -> ProposalState:
        """生成最终的参考文献部分"""
        reference_section = self.generate_reference_section(state)
        
        # 将参考文献作为独立部分保存
        state["final_references"] = reference_section
        logging.info("✅ 参考文献部分生成完成")
        
        return state

    def should_continue(self, state: ProposalState) -> str:
        """决定是否继续执行或进入写作阶段"""
        current_step = state.get("current_step", 0)
        execution_plan = state.get("execution_plan", [])
        execution_memory = state.get("execution_memory", [])
        max_iterations = state.get("max_iterations", 10)
        
        # 检查是否达到最大迭代次数
        if len(execution_memory) >= max_iterations:
            logging.info("达到最大迭代次数，进入写作阶段")
            return "write_introduction"
        
        # 检查是否还有步骤要执行
        if current_step < len(execution_plan):
            return "execute_step"
        
        # 检查是否收集到足够的信息
        arxiv_papers = state.get("arxiv_papers", [])
        web_results = state.get("web_search_results", [])
        
        logging.info(f"当前收集情况: {len(arxiv_papers)} 篇论文, {len(web_results)} 条网络结果")
        
        # 如果已经收集到足够的信息，进入写作阶段
        if len(arxiv_papers) >= 3 or len(web_results) >= 3:
            logging.info("已收集到足够信息，进入写作阶段")
            return "write_introduction"
        
        # 检查最近的执行结果
        recent_results = execution_memory[-3:] if len(execution_memory) >= 3 else execution_memory
        successful_results = [r for r in recent_results if r.get("success", False)]
        
        # 如果最近的结果都不成功，重新规划
        if len(successful_results) < len(recent_results) * 0.3:
            logging.info("最近执行结果不理想，重新规划...")
            state["current_step"] = 0
            return "plan_analysis"
        
        # 如果执行了一轮但信息不足，继续规划
        if len(arxiv_papers) < 3 and len(web_results) < 3:
            logging.info("信息收集不足，继续规划...")
            state["current_step"] = 0
            return "plan_analysis"
        
        # 默认进入写作阶段
        return "write_introduction"
    
    
    
    def _build_workflow(self) -> StateGraph:
        """构建工作流图"""
        workflow = StateGraph(ProposalState)
        
        # 添加节点
        workflow.add_node("create_master_plan", self.create_master_plan_node)
        workflow.add_node("plan_analysis", self.plan_analysis_node)
        workflow.add_node("execute_step", self.execute_step_node)
        workflow.add_node("write_introduction", self.write_introduction_node)
        workflow.add_node("write_literature_review", self.write_literature_review_node)
        workflow.add_node("write_research_design", self.write_research_design_node)
        workflow.add_node("generate_final_references", self.generate_final_references_node)
        
        # 定义流程
        workflow.set_entry_point("create_master_plan")
        workflow.add_edge("create_master_plan", "plan_analysis")
        
        # 条件边：根据执行情况决定下一步
        workflow.add_conditional_edges(
            "plan_analysis",
            lambda state: "execute_step",  # 生成计划后执行步骤
            {"execute_step": "execute_step"}
        )
        
        workflow.add_conditional_edges(
            "execute_step",
            self.should_continue,  # 根据执行结果决定下一步
            {
                "execute_step": "execute_step",  # 继续执行下一步
                "plan_analysis": "plan_analysis",  # 重新规划
                "write_introduction": "write_introduction" 
            }
        )
        
        workflow.add_edge("write_introduction", "write_literature_review")
        workflow.add_edge("write_literature_review", "write_research_design")
        workflow.add_edge("write_research_design", "generate_final_references")
        workflow.add_edge("generate_final_references", END)
        
        return workflow.compile()
    
    def generate_proposal(self, research_field: str) -> Dict[str, Any]:
        """生成研究计划书"""
        initial_state = ProposalState(
            research_field=research_field,
            query="",
            arxiv_papers=[],
            web_search_results=[],
            background="",
            objectives="",
            methodology="",
            timeline="",
            expected_outcomes="",
            final_proposal="",
            messages=[],
            research_plan="",
            available_tools=[],
            execution_plan=[],
            execution_memory=[],
            current_step=0,
            max_iterations=10,
            introduction="",
            literature_review="",
            research_design="",
            timeline_plan="",
            expected_results="",
            reference_list=[],  # 初始化统一参考文献列表
            ref_counter=1,      # 初始化参考文献计数器
            final_references="" # 添加最终参考文献字段
        )
        
        logging.info(f"🚀 开始处理研究问题: '{research_field}'")
        result = self.workflow.invoke(initial_state)
        return result


"""
TODO: 已完成简单的搜索功能等内容
下一步：生成报告相关
"""

if __name__ == "__main__":
    agent = ProposalAgent()
    research_question = "人工智能在抑郁症领域的应用"
    result = agent.generate_proposal(research_question)
    print("\n" + "="*60)
    # print("计划:")
    # print(result["research_plan"])
    print("\n" + "="*60)
    print(f"执行历史: {len(result['execution_memory'])} 个步骤")
    for memory in result["execution_memory"]:
        print(f"- {memory['description']}: {'成功' if memory['success'] else '失败'}")
    print("\n" + "="*60)
    print(f"收集到的论文: {len(result['arxiv_papers'])} 篇")
    print(f"网络搜索结果: {len(result['web_search_results'])} 条")
    print(f"统一参考文献: {len(result['reference_list'])} 条")
    print("\n" + "="*60)
    print("引言部分:")
    print(result["introduction"])
    print("\n" + "="*60)
    print("文献综述部分:")
    print(result["literature_review"])
    print("\n" + "="*60)
    print("研究设计部分:")
    print(result["research_design"])
    print("\n" + "="*60)
    print("参考文献部分:")
    print(result["final_references"])