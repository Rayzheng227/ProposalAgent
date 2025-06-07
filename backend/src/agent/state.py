"""
Agent生成过程中的所有状态
"""
from typing import TypedDict, List, Dict, Any

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
    final_proposal: str # Potentially redundant, consider removing if final_report_markdown is comprehensive
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
    timeline_plan: str # Note: This might be redundant if CONCLUSION_PROMPT handles timeline
    expected_results: str # Note: This might be redundant if CONCLUSION_PROMPT handles expected outcomes
    reference_list: List[Dict]  # 统一的参考文献列表
    ref_counter: int  # 参考文献计数器
    final_references: str  # 最终的参考文献部分
    conclusion: str # 新增结论字段
    final_report_markdown: str # 新增最终报告Markdown内容字段
    clarification_questions: List[str] # 新增：代理生成的澄清问题
    user_clarifications: str # 新增：用户对澄清问题的回答