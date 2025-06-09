"""
Agent生成过程中的图相关：节点
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
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
from backend.src.agent.prompts import * # 确保 CLARIFICATION_QUESTION_PROMPT 从这里导入
import fitz
from dotenv import load_dotenv
from .tools import search_arxiv_papers_tool,search_crossref_papers_tool,search_web_content_tool,summarize_pdf
from .state import ProposalState


load_dotenv()
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ]
)

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
        # os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

        self.tools = [search_arxiv_papers_tool, search_web_content_tool, search_crossref_papers_tool, summarize_pdf]
        self.tools_description = self.load_tools_description()
        self.agent_with_tools = create_react_agent(self.llm, self.tools)
        self.workflow = self._build_workflow() # _build_workflow is called here

    
    def load_tools_description(self) -> List[Dict]:
        """从JSON文件加载工具描述"""
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        tools_json_path = os.path.join(current_script_dir, 'tools.json')
        try:
            with open(tools_json_path, 'r', encoding='utf-8') as f:
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
    

    def clarify_research_focus_node(self, state: ProposalState) -> ProposalState:
        """根据研究领域生成澄清问题，或处理用户提供的澄清信息"""
        research_field = state["research_field"]
        user_clarifications = state.get("user_clarifications", "")
        existing_questions = state.get("clarification_questions", [])

        if user_clarifications:
            logging.info(f"🔍 用户已提供研究方向的澄清信息: {user_clarifications[:200]}...")
            # 用户已提供澄清，无需再生成问题
            state["clarification_questions"] = [] # 清空旧问题（如果有）
            return state
        
        if existing_questions:
            logging.info("📝 已存在澄清问题，等待用户回应。")
            # 如果已有问题但无用户回应，则不重复生成
            return state

        logging.info(f"🤔 正在为研究领域 '{research_field}' 生成澄清性问题...")
        
        prompt = CLARIFICATION_QUESTION_PROMPT.format(research_field=research_field)
        response = self.llm.invoke([HumanMessage(content=prompt)])
        
        generated_questions_text = response.content.strip()
        questions = [q.strip() for q in generated_questions_text.split('\n') if q.strip()]
        
        if questions:
            state["clarification_questions"] = questions
            logging.info("✅ 成功生成澄清性问题：")
            for i, q in enumerate(questions):
                logging.info(f"  {i+1}. {q}")
            logging.info("📢 请用户针对以上问题提供回应，并在下次请求时通过 'user_clarifications' 字段传入。")
        else:
            logging.warning("⚠️ 未能从LLM响应中解析出澄清性问题。")
            state["clarification_questions"] = []
            
        return state

    def create_master_plan_node(self, state: ProposalState) -> ProposalState:
        """首先基于问题去创建一个总体的规划(不同于Proposal)"""
        research_field_original = state["research_field"]
        user_clarifications = state.get("user_clarifications", "")
        tools_info = self.get_tools_info_text()

        clarification_text_for_prompt = ""
        if user_clarifications:
            clarification_text_for_prompt = (
                f"\n\n重要参考：用户为进一步聚焦研究方向，提供了以下澄清信息。在制定计划时，请务必仔细考虑这些内容：\n"
                f"{user_clarifications}\n"
            )
            logging.info("📝 正在使用用户提供的澄清信息来指导总体规划。")

        # 修改 master_plan_instruction 提示字符串
        # 目标插入位置：在 "Research Field: {research_field}" 行之后
        # 以及 "Available Tools:" 之前
        
        base_prompt_template = master_plan_instruction # 从 prompts.py 导入

        lines = base_prompt_template.splitlines()
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if "{research_field}" in line and clarification_text_for_prompt:
                # 在包含 {research_field} 的行之后插入澄清信息
                new_lines.append(clarification_text_for_prompt)
                inserted = True
        
        if not inserted and clarification_text_for_prompt: # 后备：如果占位符未找到，则追加
            new_lines.append(clarification_text_for_prompt)
            
        modified_master_plan_prompt_template = "\n".join(new_lines)
        
        master_planning_prompt = modified_master_plan_prompt_template.format(
            research_field=research_field_original, # 此处使用原始研究领域
            tools_info=tools_info
        )

        logging.info(f"🤖 Agent正在为 '{research_field_original}' (已考虑用户澄清) 制定总体研究计划...")
        response = self.llm.invoke([HumanMessage(content=master_planning_prompt)])
        
        state["research_plan"] = response.content
        state["available_tools"] = self.tools_description
        state["execution_memory"] = []
        state["current_step"] = 0
        state["max_iterations"] = 10 # 可以考虑调整，因为澄清步骤可能消耗一次迭代的意图

        logging.info("✅ 总体研究计划制定完成")
        logging.info(f"研究计划内容 (部分): {state['research_plan'][:300]}...")

        return state
    
    # Ensure this method is correctly indented as part of the ProposalAgent class
    def _decide_after_clarification(self, state: ProposalState) -> str:
        """Determines the next step after the clarification node."""
        if state.get("clarification_questions") and not state.get("user_clarifications"):
            logging.info("❓ Clarification questions generated. Waiting for user input.")
            return "end_for_user_input" 
        logging.info("✅ No clarification needed or clarifications provided. Proceeding to master plan.")
        return "proceed_to_master_plan"


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
        # logging.info("生成计划", response.content)
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
                    
            elif action_name == "search_crossref_papers":
                result = search_crossref_papers_tool.invoke(parameters)
                # 将结果保存到状态中
                if isinstance(result, list) and len(result) > 0:
                    state["web_search_results"].extend(result)
                    
            elif action_name == "summarize_pdf":
                # 改进PDF摘要的路径处理
                pdf_path = parameters.get("path", "")
                
                # 如果没有指定具体路径，尝试找到已下载的PDF
                if not pdf_path or not os.path.exists(pdf_path):
                    # 查找已下载的PDF文件
                    available_pdfs = []
                    for paper in state.get("arxiv_papers", []):
                        if paper.get("local_pdf_path") and os.path.exists(paper["local_pdf_path"]):
                            available_pdfs.append(paper["local_pdf_path"])
                    
                    if available_pdfs:
                        pdf_path = available_pdfs[0]  # 使用第一个可用的PDF
                        logging.info(f"📄 使用可用的PDF文件: {pdf_path}")
                    else:
                        logging.warning("❌ 没有找到可用的PDF文件进行摘要")
                        result = {"error": "没有找到可用的PDF文件"}
                
                if pdf_path and os.path.exists(pdf_path):
                    result = summarize_pdf.invoke({"path": pdf_path})
                    # PDF摘要结果可以存储到执行记录中，或者添加到论文信息中
                    if result and "error" not in result:
                        # 将摘要添加到对应的论文信息中
                        for paper in state["arxiv_papers"]:
                            if paper.get("local_pdf_path") == pdf_path:
                                paper["detailed_summary"] = result["summary"]
                                break
            
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
                        "summary": paper.get('detailed_summary', paper.get('summary', ''))  # 优先使用详细摘要
                    })
                    ref_counter += 1
        
        # 处理网络搜索结果和CrossRef结果
        for result in web_results:
            if "error" not in result:
                result_title = result.get('title', result.get('url', 'Unknown'))
                existing_ref = next((ref for ref in reference_list if ref.get('title') == result_title), None)
                
                if not existing_ref:
                    # 区分CrossRef和普通Web结果
                    if result.get('doi'):  # CrossRef结果
                        reference_list.append({
                            "id": ref_counter,
                            "type": "CrossRef",
                            "title": result_title,
                            "authors": result.get('authors', []),
                            "doi": result.get('doi', ''),
                            "journal": result.get('journal', ''),
                            "published": result.get('published', ''),
                            "url": result.get('url', '')
                        })
                    else:  # 普通Web结果
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
            elif ref["type"] == "CrossRef":
                # CrossRef论文格式
                authors_str = ", ".join(ref["authors"]) if ref["authors"] else "未知作者"
                ref_text += f"[{ref['id']}] {authors_str}. {ref['title']}. {ref['journal']} ({ref['published']}). DOI: {ref['doi']}\n\n"
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
        7. 使用`# 引言`作为开头
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
        
        **研究计划概要：**
        {research_plan}
        
        **已完成的引言部分：**
        {introduction_content}
        
        **已完成的文献综述部分：**
        {literature_review_content}
        
        **已收集的文献和信息（用于可能的引用）：**
        {literature_summary}
        
        {citation_instruction}
        
        {coherence_instruction}
        
        请基于以上信息，按照instruction的要求，为“{research_field}”这个研究主题撰写一个学术规范的研究设计部分。
        重点关注研究数据、方法、工作流程和局限性。
        必须**使用中文撰写**
        **不要包含时间安排或预期成果总结，这些将在结论部分统一阐述。**
        """
        
        logging.info("🔬 正在生成研究计划书研究设计部分...")
        response = self.llm.invoke([HumanMessage(content=research_design_prompt)])
        
        state["research_design"] = response.content
        logging.info("✅ 研究设计部分生成完成")
        
        return state


    def write_conclusion_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的结论部分"""
        research_field = state["research_field"]
        introduction_content = state.get("introduction", "")
        literature_review_content = state.get("literature_review", "")
        research_design_content = state.get("research_design", "")
        
        conclusion_prompt_text = f"""
        {CONCLUSION_PROMPT.format(research_field=research_field)}

        **研究主题：** {research_field}

        **已完成的引言部分摘要（用于回顾研究问题和背景）：**
        {introduction_content[:1000]}... 

        **已完成的文献综述部分摘要（用于回顾理论框架）：**
        {literature_review_content[:1000]}...

        **已完成的研究设计部分摘要（用于回顾方法和流程）：**
        {research_design_content[:1000]}...

        请基于以上提供的引言、文献综述和研究设计内容，撰写一个连贯的结论部分。
        结论应包含时间轴、预期成果和最终总结。
        确保结论与前面章节提出的研究问题、方法论和目标保持一致。
        必须使用**中文**撰写
        """
        
        logging.info("📜 正在生成研究计划书结论部分...")
        response = self.llm.invoke([HumanMessage(content=conclusion_prompt_text)])
        
        state["conclusion"] = response.content
        logging.info("✅ 结论部分生成完成")
        
        return state


    def generate_final_references_node(self, state: ProposalState) -> ProposalState:
        """生成最终的参考文献部分"""
        reference_section = self.generate_reference_section(state)
        
        # 将参考文献作为独立部分保存
        state["final_references"] = reference_section
        logging.info("✅ 参考文献部分生成完成")
        
        return state

    def generate_final_report_node(self, state: ProposalState) -> ProposalState:
        """生成最终的Markdown研究计划书报告"""
        logging.info("📄 正在生成最终的研究计划书Markdown报告...")
        
        research_field = state.get("research_field", "未知领域")
        introduction = state.get("introduction", "无引言内容")
        literature_review = state.get("literature_review", "无文献综述内容")
        research_design = state.get("research_design", "无研究设计内容")
        conclusion = state.get("conclusion", "无结论内容")
        final_references = state.get("final_references", "无参考文献")
        
        research_plan = state.get("research_plan", "无初始研究计划")
        execution_memory = state.get("execution_memory", [])
        
        # 创建output文件夹
        output_dir = "./output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 用uuid替换时间戳
        uuid = state["proposal_id"]
        #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_research_field = "".join(c for c in research_field if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')[:30]
        report_filename = f"Research_Proposal_{safe_research_field}_{uuid}.md"
        report_filepath = os.path.join(output_dir, report_filename)
        
        # 构建Markdown内容
        report_content = f"# 研究计划书：{research_field}\n\n"
        
        # report_content += "## 1. 引言\n\n"
        report_content += f"{introduction}\n\n"
        
        # report_content += "## 2. 文献综述\n\n"
        report_content += f"{literature_review}\n\n"
        
        # report_content += "## 3. 研究设计与方法\n\n"
        report_content += f"{research_design}\n\n"
        
        # report_content += "## 4. 结论与展望\n\n" # 结论部分已包含时间轴和预期成果
        report_content += f"{conclusion}\n\n"
        
        report_content += f"{final_references}\n\n" # 参考文献部分自带 "## 参考文献" 标题
        
        report_content += "---\n"
        report_content += "## 附录：过程资料\n\n"
        
        report_content += "### A.1 初始研究计划\n\n"
        report_content += "```markdown\n"
        report_content += f"{research_plan}\n"
        report_content += "```\n\n"
        
        report_content += "### A.2 执行步骤记录\n\n"
        if execution_memory:
            for i, step_memory in enumerate(execution_memory):
                action = step_memory.get("action", "未知动作")
                desc = step_memory.get("description", "无描述")
                res = step_memory.get("result", "无结果")
                success_status = "成功" if step_memory.get("success") else "失败"
                report_content += f"**步骤 {i+1}: {desc}** ({action})\n"
                report_content += f"- 状态: {success_status}\n"
                report_content += f"- 结果摘要: {str(res)[:150]}...\n\n"
        else:
            report_content += "无执行记录。\n\n"
            
        report_content += "### A.3 收集的文献与信息摘要\n\n"
        report_content += self.get_literature_summary_with_refs(state) + "\n\n"

        try:
            with open(report_filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logging.info(f"✅ 最终报告已保存到: {report_filepath}")
            state["final_report_markdown"] = report_content
        except Exception as e:
            logging.error(f"❌ 保存最终报告失败: {e}")
            state["final_report_markdown"] = "报告生成失败"
            
        return state

    def should_continue(self, state: ProposalState) -> str:
        """决定是否继续执行或进入写作阶段"""
        # 新增：如果刚生成了澄清问题且用户尚未回应，则应提示用户回应
        if state.get("clarification_questions") and not state.get("user_clarifications"):
            # 在实践中，图应该在此处暂停或结束，等待用户输入。
            # 对于当前单次调用模型，我们将允许其继续，但总体规划会受影响。
            # 或者，可以设计一个特殊的结束状态，提示需要用户输入。
            # 为简单起见，我们让它继续，但总体规划可能不够聚焦。
            # 一个更好的方法是，如果clarification_questions存在，则在此处返回一个特殊信号
            # 让调用者知道需要用户输入。但当前langgraph的should_continue通常用于工具执行循环。
            # logging.info("⏳ 等待用户对澄清问题的回应。继续当前流程，但建议提供澄清以获得更佳结果。")
            # 如果澄清问题已生成但用户未提供澄清，则不应直接进入工具执行或写作
            # 理想情况下，这里应该有一个分支逻辑，如果澄清问题存在且无答案，则图应该结束并返回问题
            # 但由于 `should_continue` 主要控制工具执行循环，我们将允许它进入plan_analysis
            # plan_analysis 和 master_plan 会基于有无澄清信息来调整行为
            pass


        current_step = state.get("current_step", 0)
        execution_plan = state.get("execution_plan", [])
        execution_memory = state.get("execution_memory", [])
        max_iterations = state.get("max_iterations", 10)
        
        # 检查是否达到最大迭代次数
        if len(execution_memory) >= max_iterations:
            logging.info(f"达到最大工具执行次数 ({max_iterations})，进入写作阶段") # 更新日志消息
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
    
    
    

    def _build_workflow(self) -> CompiledStateGraph:

        """构建工作流图"""
        workflow = StateGraph(ProposalState)
        
        # 添加节点
        workflow.add_node("clarify_research_focus", self.clarify_research_focus_node) 
        workflow.add_node("create_master_plan", self.create_master_plan_node)
        workflow.add_node("plan_analysis", self.plan_analysis_node)
        workflow.add_node("execute_step", self.execute_step_node)
        workflow.add_node("write_introduction", self.write_introduction_node)
        workflow.add_node("write_literature_review", self.write_literature_review_node)
        workflow.add_node("write_research_design", self.write_research_design_node)
        workflow.add_node("write_conclusion", self.write_conclusion_node) 
        workflow.add_node("generate_final_references", self.generate_final_references_node)
        workflow.add_node("generate_final_report", self.generate_final_report_node) 
        
        # 定义流程
        workflow.set_entry_point("clarify_research_focus") 
        
        # Conditional edge after clarification
        workflow.add_conditional_edges(
            "clarify_research_focus",
            self._decide_after_clarification, # This is where the method is called
            {
                "end_for_user_input": END, 
                "proceed_to_master_plan": "create_master_plan"
            }
        )
        
        workflow.add_edge("create_master_plan", "plan_analysis")
        
        # 条件边：根据执行情况决定下一步
        workflow.add_conditional_edges(
            "plan_analysis",
            lambda state: "execute_step",  
            {"execute_step": "execute_step"}
        )
        
        workflow.add_conditional_edges(
            "execute_step",
            self.should_continue,  
            {
                "execute_step": "execute_step",  
                "plan_analysis": "plan_analysis",  
                "write_introduction": "write_introduction" 
            }
        )
        
        workflow.add_edge("write_introduction", "write_literature_review")
        workflow.add_edge("write_literature_review", "write_research_design")
        workflow.add_edge("write_research_design", "write_conclusion") 
        workflow.add_edge("write_conclusion", "generate_final_references") 
        workflow.add_edge("generate_final_references", "generate_final_report") 
        workflow.add_edge("generate_final_report", END) 
        
        return workflow.compile() 
    


    def generate_proposal(self, research_field: str, proposal_id: str, user_clarifications: str = "") -> Dict[str, Any]:
        """生成研究计划书"""
        initial_state = ProposalState(
            research_field=research_field,
            user_clarifications=user_clarifications, # 新增：接收用户澄清
            clarification_questions=[], # 新增：初始化澄清问题列表
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
            final_references="", 
            conclusion="",       
            final_report_markdown="" # 初始化最终报告字段

        )
        initial_state["proposal_id"] = proposal_id
        logging.info(f"🚀 开始处理研究问题: '{research_field}'")
        result = self.workflow.invoke(initial_state)
        return result