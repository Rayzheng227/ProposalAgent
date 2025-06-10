"""
Agent生成过程中的所有状态
"""
from typing import TypedDict, List, Dict, Any

class ProposalState(TypedDict):
    """
    状态字典，用于在LangGraph中传递信息。
    """
    proposal_id: str # 新增：用于唯一标识一次完整的任务流程，对长期记忆和线程管理至关重要
    research_field: str # 用户输入的研究领域
    query: str
    arxiv_papers: List[Dict]
    web_search_results: List[Dict]
    background: str
    objectives: str
    methodology: str
    timeline: str
    expected_outcomes: str
    final_proposal: str
    messages: list
    
    # 澄清式问题相关字段
    clarification_questions: List[str]  # Agent生成的问题
    user_clarifications: str  # 用户提供的澄清信息

    # 计划和执行
    research_plan: str # LLM生成的总体研究计划
    available_tools: List[Dict] # 可用工具的描述
    execution_plan: List[Dict] # LLM生成的具体执行步骤
    execution_memory: List[Dict] # 存储每一步的执行结果

    # 短期记忆
    history_summary: str # 执行历史的摘要

    # 流程控制
    current_step: int # 当前执行到第几步
    max_iterations: int # 最大迭代次数

    # 报告内容
    introduction: str # 引言部分
    literature_review: str # 文献综述部分
    research_design: str # 研究设计部分
    conclusion: str # 结论、时间线和预期成果
    final_references: str # 最终格式化的参考文献部分
    final_report_markdown: str # 最终的Markdown报告

    # 统一参考文献管理
    reference_list: List[Dict] # 统一的参考文献列表
    ref_counter: int # 参考文献的全局唯一ID计数器

    timeline_plan: str # Note: This might be redundant if CONCLUSION_PROMPT handles timeline
    expected_results: str # Note: This might be redundant if CONCLUSION_PROMPT handles expected outcomes
    final_references: str  # 最终的参考文献部分
    final_report_markdown: str # 新增最终报告Markdown内容字段
    proposal_id: str #唯一标识生成的md
    clarification_questions: List[str] # 新增：代理生成的澄清问题
    user_clarifications: str # 新增：用户对澄清问题的回答
