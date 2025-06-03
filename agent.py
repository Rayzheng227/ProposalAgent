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

        master_planning_prompt = f"""
        你是一个资深的科研专家和项目规划师。用户提出了一个研究问题或领域："{research_field}"

        你有以下的工具可以使用:{tools_info}

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
        state["available_tools"] = self.tools_description
        state["execution_memory"] = []
        state["current_step"] = 0
        state["max_iterations"] = 10

        logging.info("✅ 总体研究计划制定完成")

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
        plan_analysis_prompt = f"""
        你是一个资深的科研专家和文献检索专家。用户了解了一个研究领域："{research_field}"，并制定了一个计划。
        请基于以下的研究计划，分析并确立接下来的步骤
        研究计划：
        {research_plan}
        你有以下的工具可以调用：{tools_info}

        {memory_text}
        
        基于上述研究计划和执行历史，请生成接下来需要执行的具体步骤。每个步骤应该是可执行的行动。
        
        请按以下JSON格式返回执行计划：
        {{
            "steps": [
                {{
                    "step_id": 1,
                    "action": "search_arxiv_papers",
                    "parameters": {{"query": "关键词", "max_results": 5}},
                    "description": "搜索ArXiv上关于xxx的论文",
                    "expected_outcome": "找到相关的学术论文"
                }},
                {{
                    "step_id": 2,
                    "action": "search_web_content",
                    "parameters": {{"query": "关键词"}},
                    "description": "搜索网络上关于xxx的最新信息",
                    "expected_outcome": "获取最新的研究动态"
                }}
            ]
        }}
        
        注意：
        1. 如果之前的执行结果不理想，请调整策略
        2. 每次最多生成3-5个步骤
        3. 步骤应该是具体的、可执行的
        4. 考虑执行历史，避免重复无效的搜索
        """
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
    

    def should_continue(self, state: ProposalState) -> str:
        """决定是否继续执行或重新规划"""
        current_step = state.get("current_step", 0)
        execution_plan = state.get("execution_plan", [])
        execution_memory = state.get("execution_memory", [])
        max_iterations = state.get("max_iterations", 10)
        
        # 检查是否达到最大迭代次数
        if len(execution_memory) >= max_iterations:
            return "end"
        
        # 检查是否还有步骤要执行
        if current_step < len(execution_plan):
            return "execute_step"
        
        # 检查最近的执行结果
        recent_results = execution_memory[-3:] if len(execution_memory) >= 3 else execution_memory
        successful_results = [r for r in recent_results if r.get("success", False)]
        
        # 如果最近的结果都不成功，或者需要更多信息，重新规划
        if len(successful_results) < len(recent_results) * 0.5:
            logging.info("最近执行结果不理想，重新规划...")
            return "plan_analysis"
        
        # 检查是否收集到足够的信息
        arxiv_papers = state.get("arxiv_papers", [])
        web_results = state.get("web_search_results", [])
        
        if len(arxiv_papers) < 3 and len(web_results) < 3:
            logging.info("信息收集不足，继续规划...")
            return "plan_analysis"
        
        return "end"
    
    
    
    def _build_workflow(self) -> StateGraph:
        """构建工作流图"""
        workflow = StateGraph(ProposalState)
        
        # 添加节点
        workflow.add_node("create_master_plan", self.create_master_plan_node)
        workflow.add_node("plan_analysis", self.plan_analysis_node)
        workflow.add_node("execute_step", self.execute_step_node)
        
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
                "end": END  # 结束
            }
        )
        
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
            max_iterations=10
        )
        
        logging.info(f"🚀 开始处理研究问题: '{research_field}'")
        result = self.workflow.invoke(initial_state)
        return result

if __name__ == "__main__":
    agent = ProposalAgent()
    research_question = "人工智能在医疗领域的应用"
    result = agent.generate_proposal(research_question)
    print("\n" + "="*60)
    print("研究计划:")
    print(result["research_plan"])
    print("\n" + "="*60)
    print(f"执行历史: {len(result['execution_memory'])} 个步骤")
    for memory in result["execution_memory"]:
        print(f"- {memory['description']}: {'成功' if memory['success'] else '失败'}")
    print("\n" + "="*60)
    print(f"收集到的论文: {len(result['arxiv_papers'])} 篇")
    print(f"网络搜索结果: {len(result['web_search_results'])} 条")