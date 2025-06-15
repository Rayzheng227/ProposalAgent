"""
Agent生成过程中的图相关：节点
"""
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, List, Dict, Any, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import json
import os
from datetime import datetime
import logging
from .prompts import *  # 确保 CLARIFICATION_QUESTION_PROMPT 从这里导入
import fitz
from dotenv import load_dotenv
from .tools import search_arxiv_papers_tool, search_crossref_papers_tool, search_web_content_tool, summarize_pdf, generate_gantt_chart_tool, search_google_scholar_site_tool
from .state import ProposalState
from ..utils.queue_util import QueueUtil
from ..utils.stream_mes_util import StreamUtil
from ..entity.stream_mes import StreamMes, StreamClarifyMes, StreamAnswerMes
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
            model="qwen-plus-latest",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0,
            streaming=True,  # 统一为流式输出
        )

        # 设置Tavily API密钥
        # os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

        self.tools = [search_arxiv_papers_tool, search_web_content_tool, search_crossref_papers_tool, summarize_pdf, generate_gantt_chart_tool, search_google_scholar_site_tool]
        self.tools_description = self.load_tools_description()
        self.agent_with_tools = create_react_agent(self.llm, self.tools)
        
        # 先编译工作流，后初始化可能有问题的组件
        print("先编译工作流...")
        self.workflow = self._build_workflow()
        
        print("再初始化向量数据库...")
        # 初始化长期记忆
        self.embedding_function = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.long_term_memory = Chroma(
            collection_name="proposal_agent_memory",
            embedding_function=self.embedding_function,
            persist_directory="./chroma_db"  # 持久化存储路径
        )

        # self.workflow = self._build_workflow()

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

        # 如果有修订指导，跳过生成澄清问题（改进流程中不需要澄清）
        if revision_guidance:
            logging.info(f"📝 检测到修订指导，跳过澄清问题生成步骤")
            state["clarification_questions"] = []
            return state

        # 原有逻辑保持不变
        if user_clarifications:
            logging.info(f"🔍 用户已提供研究方向的澄清信息: {user_clarifications[:200]}...")
            # 用户已提供澄清，无需再生成问题
            state["clarification_questions"] = []  # 清空旧问题（如果有）
            return state

        if existing_questions:
            logging.info("📝 已存在澄清问题，等待用户回应。")
            # 如果已有问题但无用户回应，则不重复生成
            return state

        # 生成新的澄清问题
        logging.info(f"🤔 正在为研究领域 '{research_field}' 生成澄清性问题...")

        prompt = CLARIFICATION_QUESTION_PROMPT.format(research_field=research_field)
        full_content = StreamUtil.transfer_stream_clarify_mes(
            stream_res=self.llm.stream([HumanMessage(prompt)]),
            proposal_id=state["proposal_id"]
        )
        questions = [q.strip() for q in full_content.split('\n') if q.strip()]

        if questions:
            state["clarification_questions"] = questions
            logging.info("✅ 成功生成澄清性问题：")
            for i, q in enumerate(questions):
                logging.info(f"  {i + 1}. {q}")
            logging.info("📢 请用户针对以上问题提供回应，并在下次请求时通过 'user_clarifications' 字段传入。")
        else:
            logging.warning("⚠️ 未能从LLM响应中解析出澄清性问题。")
            state["clarification_questions"] = []

        # 等待用户输入最多60秒
        wait_seconds = 60
        logging.info(f"⏳ 开始等待用户输入，最长 {wait_seconds} 秒...")

        for i in range(wait_seconds):
            # 检查是否有用户输入
            user_clarification = QueueUtil.get_clarification(state["proposal_id"])
            if user_clarification:
                state["user_clarifications"] = user_clarification
                logging.info(f"✅ 在等待 {i + 1} 秒后检测到用户输入，立即返回")
                return state
            # 每秒检查一次
            time.sleep(1)

        logging.info(f"⏰ 已等待 {wait_seconds} 秒，未收到用户输入")
        return state

    def create_master_plan_node(self, state: ProposalState) -> ProposalState:
        """首先基于问题去创建一个总体的规划"""
        state["global_step_num"] += 1
        start_time = time.time()

        research_field_original = state["research_field"]
        user_clarifications = state.get("user_clarifications", "")
        revision_guidance = state.get("revision_guidance", "")  # 获取修订指导
        tools_info = self.get_tools_info_text()

        # --- 从长期记忆中检索相关信息 ---
        logging.info(f"🔍 正在从长期记忆中检索与 '{research_field_original}' 相关的信息...")
        try:
            retrieved_docs = self.long_term_memory.similarity_search(research_field_original, k=2)  # 检索最相关的2个
        except Exception as e:
            logging.warning(f"⚠️ 从长期记忆中检索信息失败: {e}")
            retrieved_docs = []

        retrieved_knowledge_text = ""
        if retrieved_docs:
            logging.info(f"✅ 从长期记忆中检索到 {len(retrieved_docs)} 条相关记录。")
            retrieved_knowledge_text += "\n\n### 供参考的历史研究项目摘要\n"
            retrieved_knowledge_text += "这是过去完成的类似研究项目，你可以借鉴它们的思路和结论，但不要照搬。\n"
            for i, doc in enumerate(retrieved_docs):
                retrieved_knowledge_text += f"\n--- 相关历史项目 {i + 1} ---\n"
                retrieved_knowledge_text += doc.page_content
                retrieved_knowledge_text += "\n--------------------------\n"        # ------------------------------------

        # 构建提示文本
        prompt_additions = []
        
        if user_clarifications:
            clarification_text = (
                f"\n\n重要参考：用户为进一步聚焦研究方向，提供了以下澄清信息。在制定计划时，请务必仔细考虑这些内容：\n"
                f"{user_clarifications}\n"
            )
            prompt_additions.append(clarification_text)
            logging.info("📝 使用用户提供的澄清信息来指导总体规划。")
            logging.info(f"📝 澄清信息长度: {len(user_clarifications)} 字符")
        else:
            logging.info("📝 无用户澄清信息")

        if revision_guidance:
            logging.info("📝 检测到修订指导，开始处理...")            # 提取修订指南的摘要部分
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
        else:
            logging.info("📝 无修订指导")

        # 构建完整提示
        logging.info("🔧 开始构建提示模板...")
        try:
            base_prompt_template = master_plan_instruction  # 从 prompts.py 导入
            logging.info(f"✅ 成功获取基础提示模板，长度: {len(base_prompt_template)} 字符")
        except NameError as e:
            logging.error(f"❌ master_plan_instruction 未定义: {e}")
            # 使用一个简单的默认模板
            base_prompt_template = """
            请为以下研究领域制定一个详细的研究计划：

            研究领域：{research_field}

            可用工具：
            {tools_info}

            请生成一个包含研究目标、方法论和预期成果的详细计划。
            """
            logging.info("✅ 使用默认提示模板")
        except Exception as e:
            logging.error(f"❌ 获取提示模板时出错: {e}")
            return state
            
        lines = base_prompt_template.splitlines()
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if "{research_field}" in line and prompt_additions:
                # 在包含 {research_field} 的行之后插入提示信息
                new_lines.extend(prompt_additions)
                inserted = True

        if not inserted and prompt_additions:  # 后备：如果占位符未找到，则追加
            new_lines.extend(prompt_additions)
            
        modified_master_plan_prompt_template = "\n".join(new_lines)
        
        master_planning_prompt = modified_master_plan_prompt_template.format(
            research_field=research_field_original,  # 此处使用原始研究领域
            tools_info=tools_info
        )
        
        # 将所有上下文信息整合到最终的提示中
        final_prompt = (
            f"{master_planning_prompt}\n"
            f"{retrieved_knowledge_text}"
        )
        
        logging.info(f"🤖 Agent正在为 '{research_field_original}' (已考虑用户澄清和历史知识) 制定总体研究计划...")
          # 添加调试信息
        logging.info(f"📋 最终提示长度: {len(final_prompt)} 字符")
        logging.info(f"📋 提示前500字符: {final_prompt[:500]}...")
        
        try:
            logging.info("🔄 开始调用LLM stream...")
            
            # 首先尝试一个简单的测试调用
            test_response = self.llm.invoke([HumanMessage("请回答：1+1等于几？")])
            logging.info(f"✅ LLM 测试调用成功: {test_response.content}")
            
            # 然后进行实际的stream调用
            stream_response = self.llm.stream([HumanMessage(final_prompt)])
            logging.info("✅ LLM stream 创建成功，开始处理响应...")
            
            full_content = StreamUtil.transfer_stream_answer_mes(
                stream_res=stream_response,
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="生成计划"
            )
            logging.info(f"✅ LLM 响应处理完成，内容长度: {len(full_content)} 字符")
            
        except Exception as e:
            logging.error(f"❌ LLM 调用失败: {str(e)}")
            import traceback
            logging.error(f"详细错误信息: {traceback.format_exc()}")
            # 设置一个默认的研究计划以避免系统完全卡死
            full_content = f"由于技术问题，无法完成详细的研究计划生成。研究主题：{research_field_original}"

        state["research_plan"] = full_content
        # response = self.llm.invoke([HumanMessage(content=final_prompt)])

        # state["research_plan"] = response.content
        state["available_tools"] = self.tools_description
        state["execution_memory"] = []
        state["history_summary"] = ""  # 重置历史摘要
        state["current_step"] = 0
        state["max_iterations"] = 10

        logging.info("✅ 总体研究计划制定完成")
        logging.info(f"研究计划内容 (部分): {state['research_plan'][:300]}...")

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )

        return state

    # Ensure this method is correctly indented as part of the ProposalAgent class
    # def _decide_after_clarification(self, state: ProposalState) -> str:
    #     """确定澄清节点后的下一步。"""
    #     revision_guidance = state.get("revision_guidance", "")
    #
    #     # 如果有修订指导，直接进入下一步
    #     if revision_guidance:
    #         logging.info("✅ 检测到修订指导，直接进入计划生成阶段。")
    #         return "proceed_to_master_plan"
    #
    #     # 原有逻辑
    #     if state.get("clarification_questions") and not state.get("user_clarifications"):
    #         logging.info("❓ Clarification questions generated. Waiting for user input.")
    #         return "end_for_user_input"
    #     logging.info("✅ No clarification needed or clarifications provided. Proceeding to master plan.")
    #     return "proceed_to_master_plan"

    def plan_analysis_node(self, state: ProposalState) -> ProposalState:
        """解析研究计划,生成可执行步骤"""
        state["global_step_num"] += 1
        start_time = time.time()

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
        full_content = StreamUtil.transfer_stream_answer_mes(
            stream_res=self.llm.stream([HumanMessage(plan_analysis_prompt)]),
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="制定步骤"
        )
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

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
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
                "search_google_scholar_site": search_google_scholar_site_tool,
            }.get(action_name)

            if tool_to_call:
                result = tool_to_call.invoke(parameters)
                # 特定于工具的状态更新
                if action_name == "search_arxiv_papers":
                    state["arxiv_papers"].extend(result or [])
                elif action_name in ["search_web_content", "search_crossref_papers", "search_google_scholar_site"]:
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
        state["global_step_num"] += 1
        start_time = time.time()

        arxiv_papers = state.get("arxiv_papers", [])
        web_results = state.get("web_search_results", [])
        reference_list = state.get("reference_list", [])
        ref_counter = state.get("ref_counter", 1)

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="参考文献处理",
            content=f"\n开始处理~~"
        ))

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

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content=f"\n✅ 成功处理Arxiv论文，共 {len(arxiv_papers)} 篇",
        ))

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

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content=f"\n✅ 成功处理网络结果和CrossRef论文，共 {len(web_results)} 篇",
        ))

        state["reference_list"] = reference_list
        state["ref_counter"] = ref_counter

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        return state

    def get_literature_summary_with_refs(self, state: ProposalState) -> str:
        """获取带有统一编号的文献摘要"""
        state["global_step_num"] += 1
        start_time = time.time()

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
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="引用编号处理",
                content=f"\n✅ 成功生成Arxiv论文引用编号，共 {len(arxiv_refs)} 篇",
            ))

        if web_refs:
            literature_summary += "\n**相关网络信息：**\n"
            for ref in web_refs:
                literature_summary += f"[{ref['id']}] {ref['title']}\n"
                literature_summary += f"   来源: {ref['url']}\n"
                literature_summary += f"   内容摘要: {ref['content_preview']}...\n\n"

            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content=f"\n✅ 成功生成网络资源和CrossRef论文引用编号，共 {len(web_refs)} 篇",
            ))

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        return literature_summary

    def generate_reference_section(self, state: ProposalState) -> str:
        """生成格式化的参考文献部分"""
        state["global_step_num"] += 1
        start_time = time.time()

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

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="格式化文献",
            content=f"\n✅ 成功生成格式化格式化后的参考文献，共 {len(reference_list)} 篇",
        ))
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        return ref_text

    def write_introduction_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的引言部分"""

        research_field = state["research_field"]
        research_plan = state["research_plan"]
        revision_guidance = state.get("revision_guidance", "")  # 获取修订指导

        rank_reference_list = self.rerank_with_llm(state)
        # 先进行重排序，但不重新分配ID
        # rank_reference_list = self.rerank_with_llm(state["research_field"], state["refe)
        # 重排序后重新分配统一的ID
        for i, ref in enumerate(rank_reference_list, 1):
            ref["id"] = i

        state["reference_list"] = rank_reference_list
        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state)

        state["global_step_num"] += 1
        start_time = time.time()

        citation_instruction = """
        **引用要求：**
        1. 当提及相关研究或观点时，必须在句末添加引用标记，格式为 [编号]
        2. 引用标记对应上述文献列表中的编号
        3. 例如：人工智能在医疗诊断中显示出巨大潜力[1]，特别是在影像识别领域[2]。
        4. 不要编造不存在的引用，只能引用上述提供的文献
        5. 如果某个观点来自多个文献，可以使用 [1,2] 的格式
        6. 你所引用的内容必须真实来自文献列表
        """
        # 构建提示，如果有修订指导则包含
        revision_instruction = ""
        if revision_guidance:
            revision_instruction = f"""
        
        **修订指导（请特别注意）：**
        {revision_guidance}
        
        请根据上述修订指导对引言部分进行针对性改进。
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
        
        **真实的文献列表**
        {state["reference_list"]}
        
        {revision_instruction}

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
        full_content = StreamUtil.transfer_stream_answer_mes(
            stream_res=self.llm.stream([HumanMessage(introduction_prompt)]),
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="生成引言"
        )
        # 只保存引言正文，不包含参考文献
        state["introduction"] = full_content
        logging.info("✅ 引言部分生成完成")

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        return state

    def write_literature_review_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的文献综述部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        introduction_content = state.get("introduction", "")

        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state)

        state["global_step_num"] += 1
        start_time = time.time()
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
        8. 你所引用的内容必须真实来自文献列表
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
        
        **真实的文献列表**
        {state["reference_list"]}
        
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
        full_content = StreamUtil.transfer_stream_answer_mes(
            stream_res=self.llm.stream([HumanMessage(literature_review_prompt)]),
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="生成综述"
        )
        # 注意：文献综述不重复添加参考文献部分，因为引言已经包含了完整的参考文献列表
        state["literature_review"] = full_content
        logging.info("✅ 文献综述部分生成完成")

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        return state

    def write_research_design_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的研究设计部分"""
        research_field = state["research_field"]
        research_plan = state["research_plan"]
        introduction_content = state.get("introduction", "")
        literature_review_content = state.get("literature_review", "")

        # 使用统一的文献摘要
        literature_summary = self.get_literature_summary_with_refs(state)

        state["global_step_num"] += 1
        start_time = time.time()
        # 生成引用指导
        citation_instruction = """
        **引用要求：**
        1. 当提及相关研究方法、理论框架或技术时，必须在句末添加引用标记，格式为 [编号]
        2. 引用标记对应文献列表中的编号
        3. 例如：本研究将采用混合方法研究设计[5]，结合定量分析和定性访谈[8,12]。
        4. 不要编造不存在的引用，只能引用已提供的文献
        5. 在描述方法论依据时要明确标注来源
        6. 对于重要的分析工具和技术框架，必须引用相关文献
        7. 你所引用的内容必须真实来自文献列表
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
        
        **真实的文献列表**
        {state["reference_list"]}
        
        请基于以上信息，按照instruction的要求，为"{research_field}"这个研究主题撰写一个学术规范的研究设计部分。
        重点关注研究数据、方法、工作流程和局限性。
        必须**使用中文撰写**
        **不要包含时间安排或预期成果总结，这些将在结论部分统一阐述。**
        """

        logging.info("🔬 正在生成研究计划书研究设计部分...")
        try:
            full_content = StreamUtil.transfer_stream_answer_mes(
                stream_res=self.llm.stream([HumanMessage(research_design_prompt)]),
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="生成研究"
            )
            state["research_design"] = full_content
            logging.info("✅ 研究设计部分生成完成")
            logging.info(f"研究设计内容长度: {len(full_content)} 字符")
        except Exception as e:
            logging.error(f"❌ 研究设计生成失败: {str(e)}")
            import traceback
            logging.error(f"详细异常信息: {traceback.format_exc()}")
            state["research_design"] = f"研究设计生成失败: {str(e)}"

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        
        # 添加调试信息，确认方法完成并准备进入下一节点
        logging.info("🔄 write_research_design_node 完成，准备进入 write_conclusion_node")
        return state

    def write_conclusion_node(self, state: ProposalState) -> ProposalState:
        """生成研究计划书的结论部分"""
        logging.info("🔄 进入 write_conclusion_node")
        state["global_step_num"] += 1
        start_time = time.time()

        research_field = state["research_field"]
        introduction_content = state.get("introduction", "")
        literature_review_content = state.get("literature_review", "")
        research_design_content = state.get("research_design", "")

        # 为结论部分也添加文献引用能力
        literature_summary = self.get_literature_summary_with_refs(state)
        
        # 结论部分的引用指导
        citation_instruction = """
        **引用要求（结论部分）：**
        1. 在总结研究意义或预期贡献时，可以适当引用相关文献来支撑观点
        2. 引用标记对应文献列表中的编号，格式为 [编号]
        3. 例如：本研究的预期成果将为该领域提供新的理论框架[1,3]，并有望在实际应用中产生重要影响[5]。
        4. 不要编造不存在的引用，只能引用已提供的文献
        5. 你所引用的内容必须真实来自文献列表
        """

        conclusion_prompt_text = f"""
        {CONCLUSION_PROMPT.format(research_field=research_field)}

        **研究主题：** {research_field}

        **已完成的引言部分摘要（用于回顾研究问题和背景）：**
        {introduction_content[:1000]}... 

        **已完成的文献综述部分摘要（用于回顾理论框架）：**
        {literature_review_content[:1000]}...

        **已完成的研究设计部分摘要（用于回顾方法和流程）：**
        {research_design_content[:1000]}...
        
        **已收集的文献和信息（用于可能的引用）：**
        {literature_summary}
        
        {citation_instruction}
        
        **真实的文献列表**
        {state["reference_list"]}

        请基于以上提供的引言、文献综述和研究设计内容，撰写一个连贯的结论部分。
        结论应包含时间轴、预期成果和最终总结。
        确保结论与前面章节提出的研究问题、方法论和目标保持一致。
        必须使用**中文**撰写
        """

        logging.info("📜 正在生成研究计划书结论部分...")
        try:
            full_content = StreamUtil.transfer_stream_answer_mes(
                stream_res=self.llm.stream([HumanMessage(conclusion_prompt_text)]),
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="生成结论"
            )
            state["conclusion"] = full_content
            logging.info("✅ 结论部分生成完成")
            logging.info(f"结论内容长度: {len(full_content)} 字符")
        except Exception as e:
            logging.error(f"❌ 结论部分生成失败: {str(e)}")
            import traceback
            logging.error(f"详细异常信息: {traceback.format_exc()}")
            state["conclusion"] = f"结论部分生成失败: {str(e)}"
            # 即使结论生成失败，也继续后续流程
            full_content = state["conclusion"]

        # 生成甘特图
        logging.info("📊 正在生成项目甘特图...")
        logging.info(f"传入甘特图工具的研究领域: {research_field}")
        logging.info(f"传入甘特图工具的结论内容长度: {len(full_content)} 字符")
        
        # 初始化甘特图字段，确保状态中存在
        if "gantt_chart" not in state:
            state["gantt_chart"] = ""
            logging.info("🔧 初始化甘特图字段")
        
        try:
            gantt_result = generate_gantt_chart_tool.invoke({
                "timeline_content": full_content,
                "research_field": research_field
            })
            
            logging.info(f"甘特图工具返回状态: {gantt_result.get('status')}")
            logging.info(f"甘特图工具返回消息: {gantt_result.get('message')}")
            
            if gantt_result.get("status") == "success":
                gantt_chart_content = gantt_result.get("gantt_chart", "")
                # 强制设置甘特图内容并验证
                state["gantt_chart"] = gantt_chart_content
                
                # 立即验证设置是否成功
                verification_content = state.get("gantt_chart", "")
                logging.info(f"✅ 甘特图设置完成，验证长度: {len(verification_content)} 字符")
                
                if gantt_chart_content and len(gantt_chart_content) > 0:
                    logging.info(f"甘特图内容预览: {gantt_chart_content[:200]}...")
                    QueueUtil.push_mes(StreamMes(state["proposal_id"], 7, "\n✅ 项目甘特图生成完成"))
                else:
                    logging.warning("⚠️ 甘特图生成成功但内容为空")
                    QueueUtil.push_mes(StreamMes(state["proposal_id"], 7, "\n⚠️ 甘特图生成成功但内容为空"))
            else:
                state["gantt_chart"] = ""
                error_msg = gantt_result.get('message', '未知错误')
                logging.warning(f"⚠️ 甘特图生成失败: {error_msg}")
                QueueUtil.push_mes(StreamMes(state["proposal_id"], 7, f"\n⚠️ 甘特图生成失败: {error_msg}"))
                
        except Exception as e:
            state["gantt_chart"] = ""
            logging.error(f"❌ 甘特图生成异常: {str(e)}")
            import traceback
            logging.error(f"详细异常信息: {traceback.format_exc()}")
            QueueUtil.push_mes(StreamMes(state["proposal_id"], 7, f"\n❌ 甘特图生成异常: {str(e)}"))

        # 最终验证并确保状态传递
        final_gantt_chart = state.get("gantt_chart", "")
        logging.info(f"结论节点结束时，state中的gantt_chart长度: {len(final_gantt_chart)} 字符")
        
        # 强制确保甘特图在状态中不会丢失
        if final_gantt_chart and len(final_gantt_chart) > 0:
            logging.info(f"state中的gantt_chart内容预览: {final_gantt_chart[:200]}...")
            # 额外保护：将甘特图也存储在另一个字段作为备份
            state["gantt_chart_backup"] = final_gantt_chart
            logging.info("🔒 已创建甘特图备份")
        else:
            logging.warning("⚠️ state中的gantt_chart为空")
            state["gantt_chart"] = ""
            state["gantt_chart_backup"] = ""

        return state

    def generate_final_references_node(self, state: ProposalState) -> ProposalState:
        """生成最终的参考文献部分"""

        reference_section = self.generate_reference_section(state)

        # 将参考文献作为独立部分保存
        state["final_references"] = reference_section
        logging.info("✅ 参考文献部分生成完成")

        # 检查并恢复甘特图状态
        gantt_chart = state.get("gantt_chart", "")
        gantt_backup = state.get("gantt_chart_backup", "")
        
        logging.info(f"参考文献节点中的甘特图长度: {len(gantt_chart)} 字符")
        logging.info(f"参考文献节点中的甘特图备份长度: {len(gantt_backup)} 字符")
        
        # 如果主甘特图丢失但备份存在，则恢复
        if not gantt_chart and gantt_backup:
            state["gantt_chart"] = gantt_backup
            logging.warning("⚠️ 主甘特图丢失，已从备份恢复")
            gantt_chart = gantt_backup
        
        if gantt_chart:
            logging.info(f"参考文献节点中的甘特图预览: {gantt_chart[:200]}...")
        else:
            logging.warning("⚠️ 参考文献节点中甘特图为空")

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
        gantt_chart = state.get("gantt_chart", "")  # 获取甘特图

        # 检查并恢复甘特图 - 使用多重检查和恢复机制
        gantt_chart = state.get("gantt_chart", "")
        gantt_backup = state.get("gantt_chart_backup", "")
        
        # 增强调试信息
        logging.info(f"生成最终报告时，获取到的gantt_chart长度: {len(gantt_chart)} 字符")
        logging.info(f"生成最终报告时，获取到的gantt_chart_backup长度: {len(gantt_backup)} 字符")
        
        # 尝试从备份恢复甘特图
        if not gantt_chart and gantt_backup:
            gantt_chart = gantt_backup
            state["gantt_chart"] = gantt_backup
            logging.warning("⚠️ 最终报告生成时主甘特图为空，已从备份恢复")

        # 创建output文件夹
        output_dir = Path(__file__).parent.parent.parent.parent / "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 用uuid替换时间戳
        proposal_id = state["proposal_id"]
        report_filename = f"Research_Proposal_{proposal_id}.md"
        references_filename = f"References_{proposal_id}.json"
        report_filepath = os.path.join(output_dir, report_filename)
        references_filepath = os.path.join(output_dir, references_filename)        # 构建Markdown内容，如果是改进版本则添加标识
        revision_guidance = state.get("revision_guidance", "")
        improvement_attempt = state.get("improvement_attempt", 0)
        
        if revision_guidance and improvement_attempt > 0:
            report_content = f"# 研究计划书：{research_field}（改进版 v{improvement_attempt}）\n\n"
            report_content += "## 改进说明\n\n"
            report_content += f"本版本基于评审意见进行了针对性改进，改进轮次：第{improvement_attempt}轮\n\n"
        else:
            report_content = f"# 研究计划书：{research_field}\n\n"

        # report_content += "## 1. 引言\n\n"
        report_content += f"{introduction}\n\n"
        report_content += f"{literature_review}\n\n"
        report_content += f"{research_design}\n\n"
        report_content += f"{conclusion}\n\n"

        # 添加甘特图部分 - 使用恢复后的甘特图
        final_gantt_chart = gantt_chart if gantt_chart else gantt_backup
        if final_gantt_chart and final_gantt_chart.strip():
            report_content += "## 项目时间规划甘特图\n\n"
            report_content += f"```mermaid\n{final_gantt_chart}\n```\n\n"
            logging.info("✅ 甘特图已添加到最终报告")
        else:
            logging.warning("⚠️ 甘特图为空或无效，未添加到报告中")

        report_content += f"{final_references}\n\n"  # 参考文献部分自带 "## 参考文献" 标题

        state["global_step_num"] += 1
        start_time = time.time()

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="生成最终报告",
            content="\n正在生成最终研究计划报告~~",
        ))
        try:
            with open(report_filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logging.info(f"✅ 最终报告已保存到: {report_filepath}")

            # 保存参考文献列表为JSON文件
            try:
                with open(references_filepath, 'w', encoding='utf-8') as ref_file:
                    json.dump(state["reference_list"], ref_file, ensure_ascii=False, indent=2)
                logging.info(f"✅ 参考文献列表已保存到: {references_filepath}")
            except Exception as ref_e:
                logging.error(f"❌ 保存参考文献列表失败: {ref_e}")

            state["final_report_markdown"] = report_content
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time)
            ))
        except Exception as e:
            logging.error(f"❌ 保存最终报告失败: {e}")
            state["final_report_markdown"] = "报告生成失败"
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content="\n\n❌ 处理失败，共耗时 %.2fs" % (time.time() - start_time)
            ))

        return state

    def review_proposal_node(self, state: ProposalState) -> ProposalState:
        """对生成的研究计划书进行评审"""
        state["global_step_num"] += 1
        start_time = time.time()
        
        # 提取需要评审的内容
        report_content = state.get("final_report_markdown", "")
        if not report_content or report_content == "报告生成失败":
            logging.warning("⚠️ 没有可评审的内容，跳过评审步骤")
            state["review_result"] = {"success": False, "error": "没有可评审的内容"}
            return state
        
        research_field = state.get("research_field", "")
        
        logging.info("🔍 开始评审研究计划书...")
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="评审计划书",
            content="\n正在评审研究计划书..."
        ))
        
        # 初始化ReviewerAgent并进行评审
        try:
            from src.reviewer.reviewer import ReviewerAgent
            reviewer = ReviewerAgent()
            review_result = reviewer.review_proposal(report_content, research_field)
            
            if review_result.get("success"):
                # 评审成功，保存评审结果
                state["review_result"] = review_result
                logging.info(f"🔍 评审成功，正在保存评审结果到状态中...")
                logging.info(f"🔍 保存的review_result keys: {list(review_result.keys())}")
                
                scores = review_result.get("llm_scores", {})
                overall_score = scores.get("总体评分", 0)
                logging.info(f"🔍 从review_result中提取的总体评分: {overall_score}")
                
                score_message = f"\n✅ 评审完成，总体评分：{overall_score}/10"
                for criterion, score in scores.items():
                    if criterion != "总体评分":
                        score_message += f"\n- {criterion}: {score}/10"
                        
                QueueUtil.push_mes(StreamAnswerMes(
                    proposal_id=state["proposal_id"],
                    step=state["global_step_num"],
                    title="",
                    content=score_message
                ))
                
                # 记录主要优缺点
                strengths = review_result.get("strengths", [])
                weaknesses = review_result.get("weaknesses", [])
                
                if strengths:
                    strength_text = "\n\n**主要优势**:\n" + "\n".join([f"- {s}" for s in strengths[:3]])
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=state["proposal_id"],
                        step=state["global_step_num"],
                        title="",
                        content=strength_text
                    ))
                    
                if weaknesses:
                    weakness_text = "\n\n**主要不足**:\n" + "\n".join([f"- {w}" for w in weaknesses[:3]])
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=state["proposal_id"],
                        step=state["global_step_num"],
                        title="",
                        content=weakness_text
                    ))
                
                # 保存评审结果到文件
                try:
                    # 创建reviews目录
                    reviews_dir = Path(__file__).parent.parent.parent.parent / "output" / "reviews"
                    if not os.path.exists(reviews_dir):
                        os.makedirs(reviews_dir)
                    
                    # 生成评审结果文件名
                    proposal_id = state["proposal_id"]
                    review_filename = f"Review_{proposal_id}.json"
                    review_filepath = os.path.join(reviews_dir, review_filename)
                    
                    # 保存评审结果为JSON文件
                    with open(review_filepath, 'w', encoding='utf-8') as review_file:
                        json.dump(review_result, review_file, ensure_ascii=False, indent=2)
                    
                    logging.info(f"✅ 评审结果已保存到: {review_filepath}")
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=state["proposal_id"],
                        step=state["global_step_num"],
                        title="",
                        content=f"\n📄 评审结果已保存到: {review_filepath}"
                    ))
                except Exception as save_e:
                    logging.error(f"❌ 保存评审结果失败: {save_e}")
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=state["proposal_id"],
                        step=state["global_step_num"],
                        title="",
                        content=f"\n⚠️ 评审结果保存失败: {save_e}"
                    ))
            else:                # 评审失败
                error_msg = review_result.get("error", "未知错误")
                logging.error(f"❌ 评审失败: {error_msg}")
                state["review_result"] = review_result
                QueueUtil.push_mes(StreamAnswerMes(
                    proposal_id=state["proposal_id"],
                    step=state["global_step_num"],
                    title="",
                    content=f"\n❌ 评审失败: {error_msg}"
                ))
    
        except Exception as e:
            logging.error(f"❌ 评审过程异常: {str(e)}")
            import traceback
            logging.error(f"详细异常信息: {traceback.format_exc()}")
            state["review_result"] = {"success": False, "error": str(e)}
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content=f"\n❌ 评审过程异常: {str(e)}"
            ))
    
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time)
        ))
        
        # 调试：确认评审结果是否正确保存到状态中
        saved_review_result = state.get("review_result", {})
        logging.info(f"🔍 评审节点结束时，状态中的review_result存在: {saved_review_result.get('success', False)}")
        if saved_review_result.get("success"):
            saved_scores = saved_review_result.get("llm_scores", {})
            saved_overall = saved_scores.get("总体评分", 0)
            logging.info(f"🔍 评审节点结束时，保存的总体评分: {saved_overall}")
        else:
            logging.warning("⚠️ 评审节点结束时，状态中没有有效的评审结果")
        
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
            logging.info(
                f"📚 已收集充足信息 ({len(arxiv_papers)} 篇论文, {len(web_results)} 条网络结果)，提前进入写作阶段")
            return "end_report"        # 7. 检查最近执行结果质量（智能重规划）
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

    def should_improve(self, state: ProposalState) -> str:
        """决定是否需要进行改进"""
    
        review_result = state.get("review_result", {})
        logging.info(f"🔍 should_improve: 检查评审结果")
        logging.info(f"review_result类型: {type(review_result)}")
        logging.info(f"review_result keys: {list(review_result.keys()) if review_result else 'None'}")
        logging.info(f"完整的review_result: {review_result}")
        
        # 详细记录获取评分的过程
        llm_scores = review_result.get("llm_scores", {})
        logging.info(f"llm_scores类型: {type(llm_scores)}")
        logging.info(f"llm_scores: {llm_scores}")
        
        overall_score = llm_scores.get("总体评分", 0)
        logging.info(f"获取到的总体评分: {overall_score} (类型: {type(overall_score)})")
          # 如果无法获取有效的评审结果，尝试从文件中读取
        if not review_result or not review_result.get("success", False):
            logging.warning("⚠️ 状态中无法获取有效的评审结果，尝试从文件中读取")
            
            try:
                # 尝试从JSON文件中读取评审结果
                proposal_id = state.get("proposal_id", "")
                if proposal_id:
                    reviews_dir = Path(__file__).parent.parent.parent.parent / "output" / "reviews"
                    review_filepath = reviews_dir / f"Review_{proposal_id}.json"
                    
                    if review_filepath.exists():
                        logging.info(f"📁 尝试从文件读取评审结果: {review_filepath}")
                        with open(review_filepath, 'r', encoding='utf-8') as f:
                            file_review_result = json.load(f)
                        
                        if file_review_result.get("success", False):
                            logging.info("✅ 成功从文件中读取到有效的评审结果")
                            review_result = file_review_result
                            # 重新获取评分信息
                            llm_scores = review_result.get("llm_scores", {})
                            overall_score = llm_scores.get("总体评分", 0)
                            logging.info(f"📁 从文件获取的总体评分: {overall_score}")
                        else:
                            logging.warning("⚠️ 文件中的评审结果也无效")
                    else:
                        logging.warning(f"⚠️ 评审结果文件不存在: {review_filepath}")
            except Exception as e:
                logging.error(f"❌ 从文件读取评审结果失败: {e}")
            
            # 如果仍然无法获取有效结果，强制进行改进
            if not review_result or not review_result.get("success", False):
                logging.warning("⚠️ 最终无法获取有效的评审结果，强制进行改进")
                return "improve"
          # 重新获取评分信息（可能从文件中更新了review_result）
        llm_scores = review_result.get("llm_scores", {})
        logging.info(f"llm_scores类型: {type(llm_scores)}")
        logging.info(f"llm_scores: {llm_scores}")
        
        overall_score = llm_scores.get("总体评分", 0)
        logging.info(f"最终获取到的总体评分: {overall_score} (类型: {type(overall_score)})")
        
        # 如果无法获取评分，强制进行改进    
        if overall_score == 0 or not isinstance(overall_score, (int, float)):
            logging.warning(f"⚠️ 无法获取有效的评审分数 ({overall_score})，强制进行改进")
            return "improve"
        
        # 设置评分阈值，低于此分数则进行改进
        improvement_threshold = 8.5
        
        # 如果已经尝试改进一次，不再进行第二次改进
        if state.get("improvement_attempt", 0) > 0:
            logging.info(f"已尝试改进 {state['improvement_attempt']} 次，不再继续改进")
            return "finalize"
        
        if overall_score < improvement_threshold:
            logging.info(f"评审得分 ({overall_score}) 低于阈值 ({improvement_threshold})，准备进行改进")
            return "improve"
        else:
            logging.info(f"评审得分 ({overall_score}) 达到或超过阈值 ({improvement_threshold})，无需改进")
            return "finalize"

    def generate_revision_guidance_node(self, state: ProposalState) -> ProposalState:
        """根据评审结果生成修订指导"""
        state["global_step_num"] += 1
        start_time = time.time()
        
        review_result = state.get("review_result", {})
        research_field = state.get("research_field", "")
        
        if not review_result.get("success", False):
            logging.warning("⚠️ 评审结果无效，无法生成修订指导")
            state["revision_guidance"] = "无有效评审结果"
            return state
        
        logging.info("📝 正在根据评审结果生成修订指导...")
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="生成修订指导",
            content="\n正在生成修订指导..."
        ))
        
        try:
            # 导入ReviewerAgent
            from src.reviewer.reviewer import ReviewerAgent
            reviewer = ReviewerAgent()
            
            # 使用ReviewerAgent生成修订指导
            guidance_result = reviewer.generate_revision_guidance(
                review_result=review_result,
                research_field=research_field
            )
            
            if guidance_result.get("success", False):
                # 将修订指导转换为文本格式
                revision_focus = guidance_result.get("revision_focus", "")
                revision_instructions = guidance_result.get("revision_instructions", [])
                
                revision_text = f"# 修订指导\n\n## 修订重点\n{revision_focus}\n\n## 修订指南\n"
                
                for i, instruction in enumerate(revision_instructions, 1):
                    target = instruction.get("target_section", "全部")
                    operation = instruction.get("operation", "修改")
                    specific = instruction.get("specific_instruction", "")
                    reason = instruction.get("reasoning", "")
                    
                    revision_text += f"### {i}. {target}部分 - {operation}\n"
                    revision_text += f"- 具体指导: {specific}\n"
                    revision_text += f"- 原因: {reason}\n\n"
                
                # 保存修订指导
                state["revision_guidance"] = revision_text
                state["revision_guidance_structured"] = guidance_result
                state["improvement_attempt"] = state.get("improvement_attempt", 0) + 1
                
                QueueUtil.push_mes(StreamAnswerMes(
                    proposal_id=state["proposal_id"],
                    step=state["global_step_num"],
                    title="",
                    content=f"\n\n✅ 修订指导生成完成:\n\n{revision_text[:500]}..."
                ))
            else:
                error_msg = guidance_result.get("error", "未知错误")
                logging.error(f"❌ 生成修订指导失败: {error_msg}")
                state["revision_guidance"] = f"生成修订指导失败: {error_msg}"
                QueueUtil.push_mes(StreamAnswerMes(
                    proposal_id=state["proposal_id"],
                    step=state["global_step_num"],
                    title="",
                    content=f"\n❌ 生成修订指导失败: {error_msg}"
                ))
    
        except Exception as e:
            logging.error(f"❌ 修订指导生成异常: {str(e)}")
            import traceback
            logging.error(f"详细异常信息: {traceback.format_exc()}")
            state["revision_guidance"] = f"修订指导生成异常: {str(e)}"
            QueueUtil.push_mes(StreamAnswerMes(                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content=f"\n❌ 修订指导生成异常: {str(e)}"
            ))
    
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time)
        ))
        return state

    def apply_improvements_node(self, state: ProposalState) -> ProposalState:
        """根据修订指导重新生成改进后的研究计划书"""
        state["global_step_num"] += 1
        start_time = time.time()
        
        # 增加改进尝试次数
        state["improvement_attempt"] = state.get("improvement_attempt", 0) + 1
        logging.info(f"🔄 开始第 {state['improvement_attempt']} 次改进尝试")
    
        revision_guidance = state.get("revision_guidance", "")
        research_field = state.get("research_field", "")
        user_clarifications = state.get("user_clarifications", "")
        proposal_id = state.get("proposal_id", "")
    
        if not revision_guidance or revision_guidance.startswith("生成修订指导失败"):
            logging.warning("⚠️ 无有效修订指导，跳过改进步骤")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content="\n⚠️ 无有效修订指导，跳过改进步骤"
            ))
            return state
    
        logging.info("🔄 正在根据修订指导重新生成研究计划书...")
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="应用改进",
            content="\n正在根据修订指导重新生成研究计划..."
        ))        # 生成新的proposal_id用于区分改进前后的版本（但消息仍推送到原proposal_id）
        improved_proposal_id = f"{proposal_id}_improved_{state.get('improvement_attempt', 1)}"
    
        # 保存原始报告
        original_report = state.get("final_report_markdown", "")
        original_report_path = ""
        try:
            # 创建output文件夹
            output_dir = Path(__file__).parent.parent.parent.parent / "output"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 保存原始报告
            original_filename = f"Research_Proposal_{proposal_id}_original.md"
            original_report_path = os.path.join(output_dir, original_filename)
            
            with open(original_report_path, 'w', encoding='utf-8') as f:
                f.write(original_report)
            
            logging.info(f"✅ 原始报告已保存到: {original_report_path}")
        except Exception as e:
            logging.error(f"❌ 保存原始报告失败: {e}")        # 直接在当前流程中重新生成内容，而不是创建新的Agent实例
        try:
            # 保存改进前的内容作为备份
            state["original_introduction"] = state.get("introduction", "")
            state["original_literature_review"] = state.get("literature_review", "")
            state["original_research_design"] = state.get("research_design", "")
            state["original_conclusion"] = state.get("conclusion", "")
            state["original_final_report"] = state.get("final_report_markdown", "")
            
            # 重新生成各个部分（基于修订指导）
            logging.info("🔄 根据修订指导重新生成引言部分...")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="改进引言",
                content=f"\n🔄 根据修订指导重新生成引言部分..."
            ))
            
            # 重新生成引言（已考虑修订指导）
            state = self.write_introduction_node(state)
            
            logging.info("🔄 根据修订指导重新生成文献综述部分...")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="改进文献综述",
                content=f"\n🔄 根据修订指导重新生成文献综述部分..."
            ))
            
            # 重新生成文献综述
            state = self.write_literature_review_node(state)
            
            logging.info("🔄 根据修订指导重新生成研究设计部分...")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="改进研究设计",
                content=f"\n🔄 根据修订指导重新生成研究设计部分..."
            ))
            
            # 重新生成研究设计
            state = self.write_research_design_node(state)
            
            logging.info("🔄 根据修订指导重新生成结论部分...")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="改进结论",
                content=f"\n🔄 根据修订指导重新生成结论部分..."
            ))
            
            # 重新生成结论
            state = self.write_conclusion_node(state)
            
            # 重新生成最终报告
            logging.info("📄 重新生成最终改进报告...")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="生成改进报告",
                content=f"\n� 重新生成最终改进报告..."
            ))
            
            state = self.generate_final_references_node(state)
            state = self.generate_final_report_node(state)
            
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content=f"\n✅ 改进后的研究计划书已重新生成完成"
            ))
            
            # 明确标记改进流程完成
            state["improvement_completed"] = True
            logging.info(f"🎯 改进流程已完成，improvement_attempt: {state.get('improvement_attempt', 0)}")
            
        except Exception as e:
            logging.error(f"❌ 应用改进异常: {str(e)}")
            import traceback
            logging.error(f"详细异常信息: {traceback.format_exc()}")
            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content=f"\n❌ 应用改进异常: {str(e)}"
            ))
            # 即使出错也标记完成，避免无限循环
            state["improvement_completed"] = True
        
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time)
        ))
        
        # 最终确认改进流程已结束，准备进入保存环节
        logging.info("🔚 apply_improvements_node 完成，准备进入 save_memory")
        return state

    def _build_workflow(self) -> StateGraph:
        """构建工作流图"""
        workflow = StateGraph(ProposalState)

        # 1. 定义所有节点
        workflow.add_node("clarify_focus", self.clarify_research_focus_node)
        workflow.add_node("create_master_plan", self.create_master_plan_node)
        workflow.add_node("plan_analysis", self.plan_analysis_node)
        workflow.add_node("execute_step", self.execute_step_node)
        workflow.add_node("summarize_history", self.summarize_history_node)  # 短期记忆节点
        workflow.add_node("add_references", self.add_references_from_data)

        # 报告生成节点
        workflow.add_node("write_introduction", self.write_introduction_node)
        workflow.add_node("write_literature_review", self.write_literature_review_node)
        workflow.add_node("write_research_design", self.write_research_design_node)
        workflow.add_node("write_conclusion", self.write_conclusion_node)
        workflow.add_node("generate_final_references", self.generate_final_references_node)
        workflow.add_node("generate_final_report", self.generate_final_report_node)
        
        # 评审和改进节点
        workflow.add_node("review_proposal", self.review_proposal_node)
        workflow.add_node("generate_revision_guidance", self.generate_revision_guidance_node)
        workflow.add_node("apply_improvements", self.apply_improvements_node)
        workflow.add_node("save_memory", self.save_to_long_term_memory_node)  # 长期记忆节点

        # 2. 设置图的入口点
        workflow.set_entry_point("clarify_focus")

        # 3. 基础流程
        workflow.add_edge("clarify_focus", "create_master_plan")
        workflow.add_edge("create_master_plan", "plan_analysis")
        workflow.add_edge("plan_analysis", "execute_step")

        # 核心执行循环
        workflow.add_conditional_edges(
            "execute_step",
            self.should_continue,
            {
                "continue": "execute_step",  # <-- 核心修改：直接返回执行下一步
                "plan_analysis": "plan_analysis",  # 如果需要重新规划
                "summarize": "summarize_history",
                "end_report": "add_references"  # 结束循环，开始整合报告

            }
        )

        # 短期记忆循环
        workflow.add_edge("summarize_history", "execute_step")  # <-- 核心修改：摘要后返回执行下一步

        # 报告生成流程
        workflow.add_edge("add_references", "write_introduction")
        workflow.add_edge("write_introduction", "write_literature_review")
        workflow.add_edge("write_literature_review", "write_research_design")
        workflow.add_edge("write_research_design", "write_conclusion")
        workflow.add_edge("write_conclusion", "generate_final_references")
        workflow.add_edge("generate_final_references", "generate_final_report")
        
        # 关键修复：直接连接评审流程，去掉未定义的check_improvements节点
        workflow.add_edge("generate_final_report", "review_proposal")
        
        # 评审后的条件分支：直接使用should_improve方法
        workflow.add_conditional_edges(
            "review_proposal",
            self.should_improve,
            {
                "improve": "generate_revision_guidance",  # 需要改进
                "finalize": "save_memory"  # 无需改进，直接保存
            }
        )
        
        # 改进流程
        workflow.add_edge("generate_revision_guidance", "apply_improvements")
        workflow.add_edge("apply_improvements", "save_memory")  # 改进后保存
        workflow.add_edge("save_memory", END)

        # 4. 编译图
        try:
            compiled_workflow = workflow.compile()
            logging.info("✅ 工作流编译成功")
            return compiled_workflow
        except Exception as e:
            logging.error(f"❌ 工作流编译失败: {e}")
            raise e

    def generate_proposal(self, research_field: str, proposal_id: str, user_clarifications: str = "",
                          revision_guidance: str = "") -> Dict[str, Any]:
        """生成研究计划书"""
        # if not proposal_id:
        #     proposal_id = f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        config = {"configurable": {"thread_id": proposal_id}}

        initial_state = {
            "research_field": research_field,
            "user_clarifications": user_clarifications,  # 新增：接收用户澄清
            "revision_guidance": revision_guidance,
            "improvement_attempt": 0,  # 记录改进次数
            "proposal_id": proposal_id,  # 新增：唯一标识符
            "clarification_questions": [],  # 新增：初始化澄清问题列表
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
            "ref_counter": 1,  # 初始化参考文献计数器
            "final_references": "",
            "conclusion": "",
            "gantt_chart": "",  # 确保甘特图字段正确初始化
            "gantt_chart_backup": "",  # 添加备份字段
            "final_report_markdown": "", # 初始化最终报告字段
            "global_step_num": 0, # 初始化全局步骤计数器
        }

        logging.info(f"🚀 开始处理研究问题: '{research_field}' (任务ID: {proposal_id})")

        result = self.workflow.invoke(initial_state, config=config)
        
        # 检查工作流是否正常完成
        # 如果已经有最终报告，说明工作流已完成，不应该再要求澄清
        has_final_report = result.get("final_report_markdown", "")
        improvement_completed = result.get("improvement_completed", False)
        
        # 只有在以下情况才返回澄清问题：
        # 1. 没有修订指导（不是改进流程）
        # 2. 没有最终报告（工作流未完成）
        # 3. 没有完成改进流程
        clarification_questions = result.get("clarification_questions", [])
        if (clarification_questions and 
            not revision_guidance and 
            not has_final_report and 
            not improvement_completed):
            logging.info("🤔 Agent生成澄清问题，等待用户输入")
            return {"clarification_questions": clarification_questions}
        
        logging.info("✅ 工作流已完成，返回最终结果")
        return result

    def summarize_history_node(self, state: ProposalState) -> ProposalState:
        """
        回顾执行历史并生成摘要。
        采用增量式摘要策略：基于旧的摘要和最新的一步来生成新摘要。
        """
        state["global_step_num"] += 1
        start_time = time.time()

        logging.info("🧠 开始生成增量式执行历史摘要...")

        execution_memory = state.get("execution_memory", [])
        if not execution_memory:
            return state  # 如果没有历史，则跳过

        old_summary = state.get("history_summary", "")
        latest_step = execution_memory[-1]  # 只取最新的一步

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
                f"- 步骤 {i + 1}: {mem.get('description', 'N/A')}, 结果: {'成功' if mem.get('success') else '失败'}, 详情: {str(mem.get('result', ''))[:150]}..."
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

        full_content = StreamUtil.transfer_stream_answer_mes(
            stream_res=self.llm.stream([SystemMessage(content=prompt)]),
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="回顾历史并生成摘要"
        )

        state["history_summary"] = full_content
        logging.info(f"✅ 生成摘要完成: {full_content}")

        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="",
            content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
        )
        return state

    def save_to_long_term_memory_node(self, state: ProposalState) -> ProposalState:
        """将最终报告的核心洞察存入长期记忆"""
        state["global_step_num"] += 1
        start_time = time.time()
        
        logging.info("💾 正在将本次研究成果存入长期记忆...")
        
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state["global_step_num"],
            title="保存成果",
            content="\n💾 正在将研究成果存入知识库..."
        ))

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
                ids=[proposal_id]  # 使用 proposal_id 作为唯一标识
            )
            # ChromaDB in-memory with persist_directory handles saving automatically on updates.
            # self.long_term_memory.persist() # 显式调用 persist() 可能不是必需的，但可以确保写入
            logging.info(f"✅ 成功将 proposal_id '{proposal_id}' 存入长期记忆。")
        except Exception as e:
            logging.error(f"❌ 存入长期记忆失败: {e}")        # 发送最终完成消息给前端
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=state["proposal_id"],
            step=state.get("global_step_num", 0),
            title="流程完成",
            content=f"\n🎉 研究计划书生成完成！\n\n📄 最终报告已保存\n📚 参考文献已整理\n💾 成果已存入知识库\n\n✅ 所有流程已完成，可以下载结果文件。\n\n⏱️ 本阶段耗时: {time.time() - start_time:.2f}s",
            is_finish=True
        ))
        
        logging.info("🏁 整个流程已完成，已通知前端")
        return state

    def rerank_with_llm(self, state: ProposalState, relevance_threshold: float = 0.6) -> List[Dict]:
        """
        使用大型语言模型（LLM）对搜索结果进行重排序。

        参数:
            research_field (str): 研究领域
            reference_list (List[Dict]): 初始搜索结果
            relevance_threshold (float): 相关性阈值比例，默认0.6（即平均分的60%）

        返回:
            List[Dict]: 重排序后的结果（保留高于平均分60%的文献）
        """
        state["global_step_num"] += 1
        start_time = time.time()

        research_field = state.get("research_field")
        reference_list = state.get("reference_list")

        if len(reference_list) < 3:
            logging.info(f"参考文件少于3条不进行重排序...")
            return reference_list

        logging.info(f"重排序 {len(reference_list)} 个文件...")

        scored_results = []  # 初始化一个空列表来存储评分后的结果

        # 定义系统提示给LLM
        system_prompt = """You are an expert at evaluating document relevance for search queries.
    Your task is to rate documents on a scale from 0 to 10 based on how well they answer the given query.
    Guidelines:
    - Score 0-2: Document is completely irrelevant
    - Score 3-5: Document has some relevant information but doesn't directly answer the query
    - Score 6-8: Document is relevant and partially answers the query
    - Score 9-10: Document is highly relevant and directly answers the query
    You MUST respond with ONLY a single integer score between 0 and 10. Do not include ANY other text."""

        # 遍历每个结果
        for i, reference in enumerate(reference_list):
            # 每处理5个文档显示进度
            if i % 5 == 0:
                logging.info(f"正在排序第 {i + 1}/{len(reference_list)} 个文件...")

            response = None  # 初始化 response 变量

            if reference["type"] == "ArXiv" or reference["type"] == "CrossRef" or reference["type"] == "Google Scholar":
                # 定义用户提示给LLM
                user_prompt = f"""Query: {research_field}
    Document: {reference.get('summary', '')}
    Rate this document's relevance to the query on a scale from 0 to 10:"""

                # 调用LLM获取评分
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                full_content = StreamUtil.transfer_stream_answer_mes(
                    stream_res=self.llm.stream(messages),
                    proposal_id=state["proposal_id"],
                    step=state["global_step_num"],
                    title="参考论文重排序"
                )

            if (reference["type"] == "Web"):
                # 定义用户提示给LLM
                user_prompt = f"""Query: {research_field}
                        Document: {reference['content_preview']}
                        Rate this document's relevance to the query on a scale from 0 to 10:"""

                # 调用LLM获取评分
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                full_content = StreamUtil.transfer_stream_answer_mes(
                    stream_res=self.llm.stream(messages),
                    proposal_id=state["proposal_id"],
                    step=state["global_step_num"],
                    title="参考网络资源重排序"
                )
                # 提取评分
            try:
                score = int(full_content)
            except Exception as e:
                logging.error(f"文件排序错误 {i}: {e}")
                score = 0  # 默认评分 0

            # 将评分和原始结果一起存储
            scored_results.append((score, reference))

        # 计算平均分
        if scored_results:
            scores = [score for score, _ in scored_results]
            average_score = sum(scores) / len(scores)
            threshold_score = average_score * relevance_threshold

            logging.info(
                f"平均评分: {average_score:.2f}, 阈值: {threshold_score:.2f} (平均分的{relevance_threshold * 100}%)")

            # 筛选高于阈值的文献
            filtered_results = [(score, ref) for score, ref in scored_results if score >= threshold_score]

            if not filtered_results:
                # 如果没有文献达到阈值，至少保留评分最高的3个
                logging.warning("没有文献达到相关性阈值，保留评分最高的3个文献")
                scored_results.sort(reverse=True, key=lambda x: x[0])
                filtered_results = scored_results[:3]
            else:
                # 按评分降序排序
                filtered_results.sort(reverse=True, key=lambda x: x[0])

            # 提取文献信息并重新分配ID
            final_reference_list = []
            for i, (score, reference) in enumerate(filtered_results, 1):
                reference_copy = reference.copy()  # 创建副本避免修改原始数据
                reference_copy["relevance_score"] = score  # 添加相关性评分
                final_reference_list.append(reference_copy)

            logging.info(f"筛选后保留 {len(final_reference_list)} 个相关文献")
            for i, ref in enumerate(final_reference_list[:5]):  # 显示前5个的评分
                logging.info(
                    f"  文献 {i + 1}: {ref.get('title', 'Unknown')[:50]}... (评分: {ref.get('relevance_score', 0)})")

            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
            )

            return final_reference_list
        else:
            logging.warning("没有评分结果，返回原始列表")

            QueueUtil.push_mes(StreamAnswerMes(
                proposal_id=state["proposal_id"],
                step=state["global_step_num"],
                title="",
                content="\n\n✅ 处理完成，共耗时 %.2fs" % (time.time() - start_time))
            )
            return reference_list

    def execute_action(self, action_name: str, action_input: Dict[str, Any], state: ProposalState) -> Tuple[Dict[str, Any], ProposalState]:
        """执行动作"""
        try:
            # 获取对应的工具函数
            tool_func = {
                "search_arxiv_papers": search_arxiv_papers_tool,
                "search_web_content": search_web_content_tool,
                "search_crossref_papers": search_crossref_papers_tool,
                "summarize_pdf": summarize_pdf,
                "generate_gantt_chart": generate_gantt_chart_tool,
                "search_google_scholar": search_google_scholar_site_tool,  # 修改工具名称
            }.get(action_name)

            if not tool_func:
                raise ValueError(f"未知或不支持的 action: {action_name}")

            # 执行工具函数
            result = tool_func(**action_input)

            # 更新状态
            if action_name == "search_arxiv_papers":
                state["arxiv_papers"].extend(result or [])
            elif action_name in ["search_web_content", "search_crossref_papers", "search_google_scholar"]:  # 更新工具名称
                state["web_search_results"].extend(result or [])
            elif action_name == "summarize_pdf" and result and "summary" in result:
                state["pdf_summaries"].append(result)
            elif action_name == "generate_gantt_chart" and result:
                state["gantt_chart"] = result
                state["gantt_chart_backup"] = result  # 保存备份

            return result, state

        except Exception as e:
            logging.error(f"执行动作 {action_name} 失败: {str(e)}")
            return {"error": str(e)}, state
