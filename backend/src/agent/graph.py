"""
Agent生成过程中的图相关：节点
"""
import time

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
from .tools import search_arxiv_papers_tool, search_crossref_papers_tool, search_web_content_tool, summarize_pdf
from .state import ProposalState
from backend.src.utils.queue_util import QueueUtil
from backend.src.utils.stream_mes_util import stream_mes_2_full_content
from ..entity.stream_mes import StreamMes
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


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
            api_key=DASHSCOPE_API_KEY,
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0,
            streaming=True,  # 统一为流式输出
        )

        # 设置Tavily API密钥
        # os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

        self.tools = [search_arxiv_papers_tool, search_web_content_tool, search_crossref_papers_tool, summarize_pdf]
        self.tools_description = self.load_tools_description()
        self.agent_with_tools = create_react_agent(self.llm, self.tools)
        
        # 初始化长期记忆
        self.embedding_function = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.long_term_memory = Chroma(
            collection_name="proposal_agent_memory",
            embedding_function=self.embedding_function,
            persist_directory="./chroma_db" # 持久化存储路径
        )
        
        self.workflow = self._build_workflow()

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
        revision_guidance = state.get("revision_guidance", "")
        
        # 如果有修订指导，跳过生成澄清问题
        if revision_guidance:
            logging.info(f"📝 检测到修订指导，跳过澄清问题生成步骤")
            state["clarification_questions"] = []
            return state
        
        # 原有逻辑保持不变
        if user_clarifications:
            state["clarification_questions"] = []
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
        """首先基于问题去创建一个总体的规划"""
        research_field_original = state["research_field"]
        user_clarifications = state.get("user_clarifications", "")
        revision_guidance = state.get("revision_guidance", "")  # 获取修订指导
        tools_info = self.get_tools_info_text()

        # --- 从长期记忆中检索相关信息 ---
        logging.info(f"🔍 正在从长期记忆中检索与 '{research_field_original}' 相关的信息...")
        try:
            retrieved_docs = self.long_term_memory.similarity_search(research_field_original, k=2) # 检索最相关的2个
        except Exception as e:
            logging.warning(f"⚠️ 从长期记忆中检索信息失败: {e}")
            retrieved_docs = []
        
        retrieved_knowledge_text = ""
        if retrieved_docs:
            logging.info(f"✅ 从长期记忆中检索到 {len(retrieved_docs)} 条相关记录。")
            retrieved_knowledge_text += "\n\n### 供参考的历史研究项目摘要\n"
            retrieved_knowledge_text += "这是过去完成的类似研究项目，你可以借鉴它们的思路和结论，但不要照搬。\n"
            for i, doc in enumerate(retrieved_docs):
                retrieved_knowledge_text += f"\n--- 相关历史项目 {i+1} ---\n"
                retrieved_knowledge_text += doc.page_content
                retrieved_knowledge_text += "\n--------------------------\n"
        # ------------------------------------

        # --- 从长期记忆中检索相关信息 ---
        logging.info(f"🔍 正在从长期记忆中检索与 '{research_field_original}' 相关的信息...")
        try:
            retrieved_docs = self.long_term_memory.similarity_search(research_field_original, k=2) # 检索最相关的2个
        except Exception as e:
            logging.warning(f"⚠️ 从长期记忆中检索信息失败: {e}")
            retrieved_docs = []
        
        retrieved_knowledge_text = ""
        if retrieved_docs:
            logging.info(f"✅ 从长期记忆中检索到 {len(retrieved_docs)} 条相关记录。")
            retrieved_knowledge_text += "\n\n### 供参考的历史研究项目摘要\n"
            retrieved_knowledge_text += "这是过去完成的类似研究项目，你可以借鉴它们的思路和结论，但不要照搬。\n"
            for i, doc in enumerate(retrieved_docs):
                retrieved_knowledge_text += f"\n--- 相关历史项目 {i+1} ---\n"
                retrieved_knowledge_text += doc.page_content
                retrieved_knowledge_text += "\n--------------------------\n"
        # ------------------------------------

        # 构建提示文本
        prompt_additions = []
        
        if user_clarifications:
            clarification_text= (
                f"\n\n重要参考：用户为进一步聚焦研究方向，提供了以下澄清信息。在制定计划时，请务必仔细考虑这些内容：\n"
                f"{user_clarifications}\n"
            )
            prompt_additions.append(clarification_text)
            logging.info("📝 使用用户提供的澄清信息来指导总体规划。")

        if revision_guidance:
            # 提取修订指南的摘要部分
            revision_summary = ""
            lines = revision_guidance.split("\n")
            in_key_issues = False
            count = 0
            
            for line in lines:
                if "需要改进的关键问题" in line:
                    in_key_issues = True
                    revision_summary += line + "\n"
                    continue
                
                if in_key_issues and line.strip() and not line.startswith("##"):
                    revision_summary += line + "\n"
                    count += 1
                    
                if count > 5 or (in_key_issues and line.startswith("##")):
                    in_key_issues = False
                    
            if not revision_summary:
                # 如果没有提取到关键问题，使用前500个字符作为摘要
                revision_summary = revision_guidance[:500] + "...(更多详细修订建议)"
                
            revision_text = (
                f"\n\n修订指导：请根据以下修订建议调整研究计划，保留原计划的优势并改进不足：\n"
                f"{revision_summary}\n"
            )
            prompt_additions.append(revision_text)
            logging.info("📝 使用评审反馈的修订指导来改进计划。")

        # 构建完整提示
        base_prompt_template = master_plan_instruction # 从 prompts.py 导入

        lines = base_prompt_template.splitlines()
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if "{research_field}" in line and prompt_additions:
                # 在包含 {research_field} 的行之后插入提示信息
                new_lines.extend(prompt_additions)
                inserted = True
        
        if not inserted and prompt_additions: # 后备：如果占位符未找到，则追加
            new_lines.extend(prompt_additions)
            
        modified_master_plan_prompt_template = "\n".join(new_lines)
        
        master_planning_prompt = modified_master_plan_prompt_template.format(
            research_field=research_field_original, # 此处使用原始研究领域
            tools_info=tools_info
        )
        
        # 将所有上下文信息整合到最终的提示中
        final_prompt = (
            f"{master_planning_prompt}\n"
            # f"{clarification_text}\n"
            f"{retrieved_knowledge_text}"
        )
        
        logging.info(f"🤖 Agent正在为 '{research_field_original}' (已考虑用户澄清和历史知识) 制定总体研究计划...")
        full_content = stream_mes_2_full_content(state["proposal_id"], 2,
                                                 self.llm.stream([HumanMessage(content=master_planning_prompt)]))
        state["research_plan"] = full_content
        # response = self.llm.invoke([HumanMessage(content=final_prompt)])
        
        # state["research_plan"] = response.content
        state["available_tools"] = self.tools_description
        state["execution_memory"] = []
        state["history_summary"] = "" # 重置历史摘要
        state["current_step"] = 0
        state["max_iterations"] = 10 

        logging.info("✅ 总体研究计划制定完成")
        logging.info(f"研究计划内容 (部分): {state['research_plan'][:300]}...")

        return state
    
    # Ensure this method is correctly indented as part of the ProposalAgent class
    def _decide_after_clarification(self, state: ProposalState) -> str:
        """确定澄清节点后的下一步。"""
        revision_guidance = state.get("revision_guidance", "")
        
        # 如果有修订指导，直接进入下一步
        if revision_guidance:
            logging.info("✅ 检测到修订指导，直接进入计划生成阶段。")
            return "proceed_to_master_plan"
            
        # 原有逻辑
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
        history_summary = state.get("history_summary", "")

        memory_text = ""
        if history_summary:
            memory_text = f"\n\n执行历史摘要:\n{history_summary}\n"
            logging.info("🧠 已使用历史摘要作为上下文。")
        else:
            # 只有在没有摘要时，才使用完整的执行历史
            execution_memory = state.get("execution_memory", [])
            if execution_memory:
                memory_text = "\n\n完整执行历史:\n"
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
        full_content = stream_mes_2_full_content(state["proposal_id"], 1,
                                                 self.llm.stream([HumanMessage(content=plan_analysis_prompt)]))
        # logging.info("生成计划", response.content)
        try:
            # 解析JSON响应
            full_content = full_content.strip()
            # 如果响应包含```json，则提取JSON部分
            if "```json" in full_content:
                start = full_content.find("```json") + 7
                end = full_content.find("```", start)
                if end != -1:
                    full_content = full_content[start:end].strip()
            elif "```" in full_content:
                start = full_content.find("```") + 3
                end = full_content.find("```", start)
                if end != -1:
                    full_content = full_content[start:end].strip()

            plan_data = json.loads(full_content)
            state["execution_plan"] = plan_data.get("steps", [])
        except json.JSONDecodeError:
            logging.error("无法解析执行计划JSON，使用默认计划")
            logging.error(f"原始响应: {full_content}...")
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
        current_step_index = state.get("current_step", 0)
        
        if current_step_index >= len(execution_plan):
            logging.info("所有计划内步骤已执行完成，无需进一步操作。")
            # This case should ideally be caught by should_continue, but as a safeguard:
            return state
        
        # 使用索引获取当前步骤，不修改原始列表
        current_action = execution_plan[current_step_index]
        action_name = current_action.get("action")
        parameters = current_action.get("parameters", {})
        description = current_action.get("description", "")
        
        logging.info(f"🚀 执行步骤 {current_step_index + 1}/{len(execution_plan)}: {description}")
        
        result = None
        memory_entry = {}
        try:
            # 根据action_name调用相应的工具
            tool_to_call = {
                "search_arxiv_papers": search_arxiv_papers_tool,
                "search_web_content": search_web_content_tool,
                "search_crossref_papers": search_crossref_papers_tool,
                "summarize_pdf": summarize_pdf,
            }.get(action_name)

            if tool_to_call:
                result = tool_to_call.invoke(parameters)
                # 特定于工具的状态更新
                if action_name == "search_arxiv_papers":
                    state["arxiv_papers"].extend(result or [])
                elif action_name in ["search_web_content", "search_crossref_papers"]:
                    state["web_search_results"].extend(result or [])
                elif action_name == "summarize_pdf" and result and "summary" in result:
                     for paper in state["arxiv_papers"]:
                        if paper.get("local_pdf_path") == parameters.get("path"):
                            paper["detailed_summary"] = result["summary"]
                            break
            else:
                result = f"未知或不支持的 action: {action_name}"
                raise ValueError(result)

            # 每次成功获取数据后更新参考文献
            state = self.add_references_from_data(state)
            
            memory_entry = {
                "step_id": current_step_index + 1,
                "action": f"{action_name}({parameters})",
                "description": description,
                "result": str(result)[:500] if result else "无结果",
                "success": True,
            }

        except Exception as e:
            logging.error(f"执行步骤 '{description}' 失败: {e}")
            memory_entry = {
                "step_id": current_step_index + 1,
                "action": f"{action_name}({parameters})",
                "description": description,
                "result": f"执行失败: {str(e)}",
                "success": False,
            }
        
        # 更新执行历史和步数计数器
        state["execution_memory"].append(memory_entry)
        state["current_step"] = current_step_index + 1
        
        logging.info(f"✅ 步骤 {state['current_step']}/{len(execution_plan)} 执行完成: {action_name}")
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
        QueueUtil.push_mes(
            StreamMes(state["proposal_id"], 3, f"\n✅ 成功处理下载的参考论文/网页资源"))

        return state

    def get_literature_summary_with_refs(self, state: ProposalState, step: int) -> str:
        """获取带有统一编号的文献摘要"""
        reference_list = state.get("reference_list", [])
        literature_summary = ""

        # 按类型分组显示
        arxiv_refs = [ref for ref in reference_list if ref.get("type") == "ArXiv"]
        web_refs = [ref for ref in reference_list if ref.get("type") == "Web"]

        if arxiv_refs:
            literature_summary += "\n\n**相关Arxiv论文：**\n"
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

        QueueUtil.push_mes(StreamMes(state["proposal_id"], step, "\n✅ 成功生成引用编号\n"))
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

        QueueUtil.push_mes(
            StreamMes(state["proposal_id"], 8, "\n✅ 成功生成参考文献"))
        return ref_text

    def write_introduction_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的引言部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]

        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state, step=4)

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
        full_content = stream_mes_2_full_content(state["proposal_id"], 4,
                                                 self.llm.stream([HumanMessage(content=introduction_prompt)]))
        # 只保存引言正文，不包含参考文献
        state["introduction"] = full_content
        logging.info("✅ 引言部分生成完成")

        return state

    def write_literature_review_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的文献综述部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        introduction_content = state.get("introduction", "")

        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state, step=5)

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
        full_content = stream_mes_2_full_content(state["proposal_id"], 5,
                                                 self.llm.stream([HumanMessage(content=literature_review_prompt)]))
        # 注意：文献综述不重复添加参考文献部分，因为引言已经包含了完整的参考文献列表
        state["literature_review"] = full_content
        logging.info("✅ 文献综述部分生成完成")

        return state

    def write_research_design_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的研究设计部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        introduction_content = state.get("introduction", "")
        literature_review_content = state.get("literature_review", "")

        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state, step=6)

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
        
        请基于以上信息，按照instruction的要求，为"{research_field}"这个研究主题撰写一个学术规范的研究设计部分。
        重点关注研究数据、方法、工作流程和局限性。
        必须**使用中文撰写**
        **不要包含时间安排或预期成果总结，这些将在结论部分统一阐述。**
        """

        logging.info("🔬 正在生成研究计划书研究设计部分...")
        full_content = stream_mes_2_full_content(state["proposal_id"], 6,
                                                 self.llm.stream([HumanMessage(content=research_design_prompt)]))

        state["research_design"] = full_content
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
        full_content = stream_mes_2_full_content(state["proposal_id"], 7,
                                                 self.llm.stream([HumanMessage(content=conclusion_prompt_text)]))
        state["conclusion"] = full_content
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
        start_timestamp = time.time()
        QueueUtil.push_mes(StreamMes(state['proposal_id'], 9, "正在生成最终研究计划报告~"))
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
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_research_field = "".join(
            c for c in research_field if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')[:30]
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

        report_content += f"{final_references}\n\n"  # 参考文献部分自带 "## 参考文献" 标题

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
                report_content += f"**步骤 {i + 1}: {desc}** ({action})\n"
                report_content += f"- 状态: {success_status}\n"
                report_content += f"- 结果摘要: {str(res)[:150]}...\n\n"
        else:
            report_content += "无执行记录。\n\n"

        report_content += "### A.3 收集的文献与信息摘要\n\n"
        report_content += self.get_literature_summary_with_refs(state, 9) + "\n\n"

        try:
            with open(report_filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logging.info(f"✅ 最终报告已保存到: {report_filepath}")
            state["final_report_markdown"] = report_content
            QueueUtil.push_mes(StreamMes(state['proposal_id'], 9, "\n✅ 报告生成完毕"))
            # 结束标记
            QueueUtil.push_mes(StreamMes(state['proposal_id'], 0, ""))
        except Exception as e:
            logging.error(f"❌ 保存最终报告失败: {e}")
            state["final_report_markdown"] = "报告生成失败"
            QueueUtil.push_mes(StreamMes(state['proposal_id'], 9, "\n❌  报告生成失败"))

        return state

    def should_continue(self, state: ProposalState) -> str:
        """决定是否继续执行或进入写作阶段"""
    
        # 1. 首先检查澄清问题状态（保留原逻辑）
        if state.get("clarification_questions") and not state.get("user_clarifications"):
            # 如果有澄清问题但用户未回应，继续执行但可能效果不佳
            logging.info("⏳ 检测到未回应的澄清问题，但继续执行流程")
            pass

        # 2. 获取基本状态信息
        current_step_index = state.get("current_step", 0)
        execution_plan = state.get("execution_plan", [])
        execution_memory = state.get("execution_memory", [])
        max_iterations = state.get("max_iterations", 10)
        max_steps = len(execution_plan)

        # 3. 检查是否超过最大迭代次数（安全上限）
        if len(execution_memory) >= max_iterations:
            logging.info(f"🛑 达到最大执行次数 ({max_iterations})，进入写作阶段")
            return "end_report"
        
        # 4. 检查是否所有计划步骤都已完成
        if current_step_index >= max_steps:
            logging.info("✅ 所有计划内步骤已执行完成，进入写作阶段")
            return "end_report"

        # 5. 每执行1步后进行历史摘要（可配置）
        summarize_interval = 1  # 可以调整这个值
        if current_step_index > 0 and current_step_index % summarize_interval == 0:
            logging.info(f"📝 执行了 {current_step_index} 步，正在生成历史摘要...")
            return "summarize"

        # 6. 检查是否收集到足够信息（提前结束条件）
        arxiv_papers = state.get("arxiv_papers", [])
        web_results = state.get("web_search_results", [])
        
        if len(arxiv_papers) >= 5 and len(web_results) >= 5:
            logging.info(f"📚 已收集充足信息 ({len(arxiv_papers)} 篇论文, {len(web_results)} 条网络结果)，提前进入写作阶段")
            return "end_report"

        # 7. 检查最近执行结果质量（智能重规划）
        if len(execution_memory) >= 3:
            recent_results = execution_memory[-3:]
            successful_results = [r for r in recent_results if r.get("success", False)]
            
            # 如果最近3步中成功率低于30%，考虑重新规划
            if len(successful_results) < len(recent_results) * 0.3:
                logging.info("⚠️ 最近执行成功率较低，重新规划...")
                state["current_step"] = 0  # 重置步数计数器
                return "plan_analysis"

        # 8. 默认继续执行下一步
        logging.info(f"🚀 继续执行步骤 {current_step_index + 1}/{max_steps}")
        return "continue"
    
    
    
    def _build_workflow(self) -> StateGraph: # This method uses _decide_after_clarification
        """构建工作流图"""
        workflow = StateGraph(ProposalState)

        # 1. 定义所有节点
        workflow.add_node("clarify_focus", self.clarify_research_focus_node)
        workflow.add_node("create_master_plan", self.create_master_plan_node)
        workflow.add_node("plan_analysis", self.plan_analysis_node)
        workflow.add_node("execute_step", self.execute_step_node)
        workflow.add_node("summarize_history", self.summarize_history_node) # 短期记忆节点
        workflow.add_node("add_references", self.add_references_from_data)

        # 报告生成节点
        workflow.add_node("write_introduction", self.write_introduction_node)
        workflow.add_node("write_literature_review", self.write_literature_review_node)
        workflow.add_node("write_research_design", self.write_research_design_node)
        workflow.add_node("write_conclusion", self.write_conclusion_node)
        workflow.add_node("generate_final_references", self.generate_final_references_node)
        workflow.add_node("generate_final_report", self.generate_final_report_node)
        workflow.add_node("save_memory", self.save_to_long_term_memory_node) # 长期记忆节点

        # 2. 设置图的入口点
        workflow.set_entry_point("clarify_focus")

        # 3. 定义图的边（流程）
        workflow.add_conditional_edges(
            "clarify_focus",
            self._decide_after_clarification,
            {
                "end_for_user_input": END,
                "proceed_to_master_plan": "create_master_plan"
            }
        )
        
        workflow.add_edge("create_master_plan", "plan_analysis")
        
        # 生成计划后，直接进入执行
        workflow.add_edge("plan_analysis", "execute_step")
        
        # 核心执行循环
        workflow.add_conditional_edges(
            "execute_step",
            self.should_continue,
            {
                "continue": "execute_step", # <-- 核心修改：直接返回执行下一步
                "plan_analysis": "plan_analysis", # 如果需要重新规划
                "summarize": "summarize_history",
                "end_report": "add_references" # 结束循环，开始整合报告

            }
        )
        
        # 短期记忆循环
        workflow.add_edge("summarize_history", "execute_step") # <-- 核心修改：摘要后返回执行下一步

        # 报告生成流程
        workflow.add_edge("add_references", "write_introduction")
        workflow.add_edge("write_introduction", "write_literature_review")
        workflow.add_edge("write_literature_review", "write_research_design")
        workflow.add_edge("write_research_design", "write_conclusion")
        workflow.add_edge("write_conclusion", "generate_final_references")
        workflow.add_edge("generate_final_references", "generate_final_report")

        # 最后，保存到长期记忆并结束
        workflow.add_edge("generate_final_report", "save_memory")
        workflow.add_edge("save_memory", END)
        
        # 4. 编译图
        return workflow.compile(checkpointer=MemorySaver())


    def generate_proposal(self, research_field: str, proposal_id: str,user_clarifications: str = "", revision_guidance: str = "") -> Dict[str, Any]:
        """生成研究计划书"""
        if not proposal_id:
            proposal_id = f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        config = {"configurable": {"thread_id": proposal_id}}

        initial_state = {
            "research_field": research_field,
            "user_clarifications": user_clarifications, # 新增：接收用户澄清
            "revision_guidance": revision_guidance,
            "proposal_id": proposal_id,  # 新增：唯一标识符
            "clarification_questions": [], # 新增：初始化澄清问题列表
            "query": "",
            "arxiv_papers": [],
            "web_search_results": [],
            "background": "",
            "objectives": "",
            "methodology": "",
            "timeline": "",
            "expected_outcomes": "",
            "final_proposal": "",
            "messages": [],
            "research_plan": "",
            "available_tools": [],
            "execution_plan": [],
            "execution_memory": [],
            "current_step": 0,
            "max_iterations": 10,
            "introduction": "",
            "literature_review": "",
            "research_design": "",
            "timeline_plan": "",
            "expected_results": "",
            "reference_list": [],  # 初始化统一参考文献列表
            "ref_counter": 1,      # 初始化参考文献计数器
            "final_references": "",
            "conclusion": "",
            "final_report_markdown": "" # 初始化最终报告字段
        }
        
        logging.info(f"🚀 开始处理研究问题: '{research_field}' (任务ID: {proposal_id})")
        
        
        QueueUtil.new_queue(proposal_id)  # 创建消息队列
        result = self.workflow.invoke(initial_state,config=config)
        clarification_questions = result.get("clarification_questions", [])
        if clarification_questions:
            logging.info(" agent生成澄清问题，等待用户输入")
            return {"clarification_questions": clarification_questions}
        
        return result

    def summarize_history_node(self, state: ProposalState) -> ProposalState:
        """
        回顾执行历史并生成摘要。
        采用增量式摘要策略：基于旧的摘要和最新的一步来生成新摘要。
        """
        logging.info("🧠 开始生成增量式执行历史摘要...")
        
        execution_memory = state.get("execution_memory", [])
        if not execution_memory:
            return state # 如果没有历史，则跳过

        old_summary = state.get("history_summary", "")
        latest_step = execution_memory[-1] # 只取最新的一步

        # 将最新步骤格式化为文本
        latest_step_text = (
            f"- 描述: {latest_step.get('description', 'N/A')}\n"
            f"- 动作: {latest_step.get('action', 'N/A')}\n"
            f"- 结果: {'成功' if latest_step.get('success') else '失败'}\n"
            f"- 详情: {str(latest_step.get('result', ''))[:200]}..."
        )

        # 如果没有旧摘要（这是第一次总结），则对目前所有的历史进行总结
        if not old_summary:
            prompt_template = """
            你是一个研究助理，正在为一项复杂的科研任务撰写第一份进度摘要。
            请根据以下到目前为止的所有执行历史，生成一段简洁、精炼的摘要。
            摘要需要捕捉到关键发现、遇到的主要障碍或失败，以及尚未解决的核心问题。

            原始研究问题: {research_field}
            
            执行历史:
            {history}

            请输出摘要:
            """
            # 格式化完整的历史记录
            full_history_text = "\n".join([
                f"- 步骤 {i+1}: {mem.get('description', 'N/A')}, 结果: {'成功' if mem.get('success') else '失败'}, 详情: {str(mem.get('result', ''))[:150]}..."
                for i, mem in enumerate(execution_memory)
            ])
            prompt = prompt_template.format(
                research_field=state['research_field'],
                history=full_history_text
            )
        else:
            # 如果有旧摘要，则进行增量更新
            prompt_template = """
            你是一个研究助理，正在实时更新一份任务进度摘要。
            你的任务是根据【上一版的摘要】和【最新完成的步骤】，生成一份【更新后的摘要】。
            请不要重复旧摘要已有的信息，重点在于整合新信息并提炼出当前最关键的发现、障碍和结论。

            【上一版的摘要】:
            {old_summary}

            【最新完成的步骤】:
            {latest_step}

            请输出一份简洁、连贯的【更新后的摘要】:
            """
            prompt = prompt_template.format(
                old_summary=old_summary,
                latest_step=latest_step_text
            )

        response = self.llm.invoke([SystemMessage(content=prompt)])
        summary = response.content.strip()
        
        state["history_summary"] = summary
        logging.info(f"✅ 生成摘要完成: {summary}")
        
        return state

    def save_to_long_term_memory_node(self, state: ProposalState) -> ProposalState:
        """将最终报告的核心洞察存入长期记忆"""
        logging.info("💾 正在将本次研究成果存入长期记忆...")
        
        proposal_id = state.get("proposal_id")
        if not proposal_id:
            logging.warning("⚠️ proposal_id 不存在，无法存入长期记忆。")
            return state

        # 生成一个用于存储的文档
        document_to_store = f"""
        研究课题: {state.get('research_field')}
        用户澄清: {state.get('user_clarifications', '无')}
        最终研究计划摘要: {state.get('research_plan', '')[:500]}...
        引言核心: {state.get('introduction', '')[:500]}...
        文献综述要点: {state.get('literature_review', '')[:500]}...
        最终结论: {state.get('conclusion', '')[:500]}...
        """
        
        try:
            self.long_term_memory.add_texts(
                texts=[document_to_store],
                metadatas=[{"proposal_id": proposal_id, "timestamp": datetime.now().isoformat()}],
                ids=[proposal_id] # 使用 proposal_id 作为唯一标识
            )
            # ChromaDB in-memory with persist_directory handles saving automatically on updates.
            # self.long_term_memory.persist() # 显式调用 persist() 可能不是必需的，但可以确保写入
            logging.info(f"✅ 成功将 proposal_id '{proposal_id}' 存入长期记忆。")
        except Exception as e:
            logging.error(f"❌ 存入长期记忆失败: {e}")
        
        return state
