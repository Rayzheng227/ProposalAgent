from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Tuple
import re
from dotenv import load_dotenv  # 添加dotenv导入

from .prompts import (
    GENERAL_REVIEW_PROMPT, 
    SECTION_REVIEW_PROMPT, 
    REVISION_GUIDANCE_PROMPT,
    FIELD_SPECIFIC_RUBRICS
)
from .scoring import (
    determine_research_field_category,
    extract_section_content,
    calculate_metadata_scores
)

# 加载环境变量
load_dotenv()
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
base_url = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

class ReviewerAgent:
    """研究计划书评审代理，负责评估ProposalAgent生成的研究计划书并提供改进建议"""
    
    def __init__(self, model: str = "qwen-plus"):
        """初始化ReviewerAgent
        
        Args:
            model: 使用的模型名称
        """
        # 直接使用从环境变量获取的API密钥
        self.llm = ChatOpenAI(
            api_key=DASHSCOPE_API_KEY,
            model=model,
            base_url=base_url,
            temperature=0
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
    def _parse_json_from_response(self, response_text: str) -> Dict:
        """从LLM响应中解析JSON数据"""
        try:
            # 尝试提取JSON部分（如果被包含在代码块中）
            json_pattern = r"```json\s*([\s\S]*?)\s*```"
            json_match = re.search(json_pattern, response_text)
            
            if json_match:
                json_content = json_match.group(1)
                return json.loads(json_content)
            
            # 如果没有JSON代码块，尝试直接解析整个响应
            return json.loads(response_text)
            
        except json.JSONDecodeError:
            self.logger.error(f"无法解析JSON响应: {response_text[:500]}...")
            self.logger.error("尝试使用正则表达式提取JSON内容...")
            
            try:
                # 尝试找到类似JSON的结构并修复常见错误
                # 去掉可能的解释性文本，只保留{}之间的部分
                json_content_match = re.search(r"({[\s\S]*})", response_text)
                if json_content_match:
                    json_content = json_content_match.group(1)
                    # 修复一些常见JSON格式错误
                    # 1. 修复未引用的键
                    json_content = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_content)
                    # 2. 修复末尾多余的逗号
                    json_content = re.sub(r',\s*}', '}', json_content)
                    json_content = re.sub(r',\s*]', ']', json_content)
                    
                    return json.loads(json_content)
            except Exception as e:
                self.logger.error(f"修复JSON失败: {str(e)}")
            
            # 如果所有尝试都失败，返回一个基本的错误对象
            return {
                "error": "无法解析响应为JSON",
                "raw_response": response_text[:1000] + ("..." if len(response_text) > 1000 else "")
            }
    
    def review_proposal(self, proposal_content: str, research_field: str) -> Dict[str, Any]:
        """评审完整的研究计划书
        
        Args:
            proposal_content: 研究计划书全文内容
            research_field: 研究领域
            
        Returns:
            评审结果字典，包含评分、优缺点和改进建议
        """
        self.logger.info(f"开始评审研究计划书: {research_field}")
        
        # 首先计算一些基于元数据的初步评分
        metadata_scores = calculate_metadata_scores(proposal_content)
        self.logger.info(f"元数据分析完成: 引用次数={metadata_scores.get('citation_count')}, " 
                        f"参考文献数={metadata_scores.get('reference_count')}")
        
        # 确定研究领域类别，获取特定评分标准
        field_category = determine_research_field_category(research_field)
        field_specific = FIELD_SPECIFIC_RUBRICS.get(field_category, FIELD_SPECIFIC_RUBRICS["default"])
        
        # 准备评审提示
        review_prompt = GENERAL_REVIEW_PROMPT.format(
            research_field=research_field,
            content_to_review=proposal_content,
            field_specific_criterion=field_specific["criterion"],
            field_specific_description=field_specific["description"]
        )
        
        # 调用LLM进行评审
        self.logger.info("正在使用LLM评估研究计划书...")
        response = self.llm.invoke([HumanMessage(content=review_prompt)])
        
        # 解析评审结果
        review_result = self._parse_json_from_response(response.content)
        
        # 确保评审结果包含必要的字段
        if "error" in review_result:
            self.logger.error(f"评审过程出错: {review_result['error']}")
            return {
                "success": False,
                "error": review_result['error'],
                "metadata_scores": metadata_scores
            }
        
        # 合并元数据评分和LLM评分
        final_result = {
            "success": True,
            "review_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "research_field": research_field,
            "field_category": field_category,
            "llm_scores": review_result.get("scores", {}),
            "metadata_scores": metadata_scores,
            "strengths": review_result.get("strengths", []),
            "weaknesses": review_result.get("weaknesses", []),
            "improvement_suggestions": review_result.get("improvement_suggestions", []),
            "overall_comments": review_result.get("overall_comments", "")
        }
        
        self.logger.info(f"评审完成，总体评分: {review_result.get('scores', {}).get('总体评分', '未知')}")
        return final_result
    
    def review_section(self, section_content: str, section_name: str, research_field: str, section_requirements: str = None) -> Dict[str, Any]:
        """评审研究计划书的特定章节
        
        Args:
            section_content: 章节内容
            section_name: 章节名称
            research_field: 研究领域
            section_requirements: 章节特定要求
            
        Returns:
            章节评审结果
        """
        if not section_requirements:
            # 设置默认的章节特定要求
            section_req_map = {
                "引言": "包含研究背景、问题陈述、研究目的和问题的重要性",
                "文献综述": "涵盖相关文献的综合分析，呈现研究现状、理论框架和研究空白",
                "研究设计": "详细说明研究方法、数据收集过程、分析方法和预期结果",
                "结论": "总结主要发现、研究价值、限制条件和未来研究方向"
            }
            section_requirements = section_req_map.get(section_name, "按学术标准评估内容完整性和质量")
        
        # 准备评审提示
        review_prompt = SECTION_REVIEW_PROMPT.format(
            research_field=research_field,
            section_name=section_name,
            section_content=section_content,
            section_specific_requirements=section_requirements
        )
        
        # 调用LLM评审章节
        self.logger.info(f"正在评估'{section_name}'章节...")
        response = self.llm.invoke([HumanMessage(content=review_prompt)])
        
        # 解析评审结果
        review_result = self._parse_json_from_response(response.content)
        
        # 确保评审结果包含必要的字段
        if "error" in review_result:
            self.logger.error(f"章节评审过程出错: {review_result['error']}")
            return {
                "success": False,
                "error": review_result['error']
            }
        
        final_result = {
            "success": True,
            "section_name": section_name,
            "section_score": review_result.get("section_score"),
            "strengths": review_result.get("strengths", []),
            "weaknesses": review_result.get("weaknesses", []),
            "specific_suggestions": review_result.get("specific_suggestions", []),
            "section_comments": review_result.get("section_comments", "")
        }
        
        self.logger.info(f"'{section_name}'章节评估完成，得分: {review_result.get('section_score', '未知')}")
        return final_result
    
    def generate_revision_guidance(self, review_result: Dict[str, Any], research_field: str, focus_areas: List[str] = None) -> Dict[str, Any]:
        """根据评审结果生成修订指导
        
        Args:
            review_result: 评审结果字典
            research_field: 研究领域
            focus_areas: 特别关注的领域列表
            
        Returns:
            修订指导字典
        """
        # 将评审结果转换为字符串
        review_feedback = json.dumps(review_result, ensure_ascii=False, indent=2)
        
        # 准备特定关注点
        if not focus_areas:
            # 基于评分自动确定关注点
            scores = review_result.get("llm_scores", {})
            lowest_scores = sorted([(k, v) for k, v in scores.items() if k != "总体评分"], key=lambda x: x[1])[:2]
            focus_areas = [f"{item[0]} (得分: {item[1]})" for item in lowest_scores]
        
        specific_focus = "特别关注以下方面：\n" + "\n".join([f"- {area}" for area in focus_areas])
        
        # 准备修订指导提示
        guidance_prompt = REVISION_GUIDANCE_PROMPT.format(
            research_field=research_field,
            review_feedback=review_feedback,
            specific_focus=specific_focus
        )
        
        # 调用LLM生成修订指导
        self.logger.info("正在生成修订指导...")
        response = self.llm.invoke([HumanMessage(content=guidance_prompt)])
        
        # 解析修订指导结果
        guidance_result = self._parse_json_from_response(response.content)
        
        # 确保结果包含必要的字段
        if "error" in guidance_result:
            self.logger.error(f"生成修订指导过程出错: {guidance_result['error']}")
            return {
                "success": False,
                "error": guidance_result['error']
            }
        
        final_guidance = {
            "success": True,
            "revision_focus": guidance_result.get("revision_focus", ""),
            "revision_instructions": guidance_result.get("revision_instructions", []),
            "content_enhancement_suggestions": guidance_result.get("content_enhancement_suggestions", {}),
            "priority_order": guidance_result.get("priority_order", [])
        }
        
        self.logger.info("修订指导生成完成")
        return final_guidance