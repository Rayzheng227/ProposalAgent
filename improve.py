from backend.src.agent.graph import ProposalAgent
from backend.src.reviewer.reviewer import ReviewerAgent
import os
import json
import argparse
import logging
import re
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

def load_review_result(review_file):
    """加载评审结果文件"""
    try:
        with open(review_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"加载评审结果失败: {e}")
        return None

def load_original_proposal(file_path):
    """加载原始研究计划书文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logging.error(f"加载原始研究计划书失败: {e}")
        return None

def extract_sections(content):
    """从原始内容中提取各个章节"""
    sections = {}
    
    # 提取引言部分
    intro_match = re.search(r'(?:# 引言|## 引言|# 1[\.、]\s*引言)(.*?)(?=# |## |$)', content, re.DOTALL)
    if intro_match:
        sections['introduction'] = intro_match.group(1).strip()
    
    # 提取文献综述
    lit_review_match = re.search(r'(?:# 文献综述|## 文献综述|# 2[\.、]\s*文献综述)(.*?)(?=# |## |$)', content, re.DOTALL)
    if lit_review_match:
        sections['literature_review'] = lit_review_match.group(1).strip()
    
    # 提取研究设计
    design_match = re.search(r'(?:# 研究设计|## 研究设计|# 3[\.、]\s*研究设计)(.*?)(?=# |## |$)', content, re.DOTALL)
    if design_match:
        sections['research_design'] = design_match.group(1).strip()
    
    # 提取结论部分
    conclusion_match = re.search(r'(?:# 结论|## 结论|# 4[\.、]\s*结论)(.*?)(?=# |## |$)', content, re.DOTALL)
    if conclusion_match:
        sections['conclusion'] = conclusion_match.group(1).strip()
    
    return sections

def format_revision_guidance(review_result, original_content=None):
    """将评审结果转换为结构化的修订指导
    
    Args:
        review_result: 评审结果字典
        original_content: 原始研究计划书内容
    """
    if not review_result or not review_result.get("success"):
        return ""
    
    # 提取关键信息
    strengths = review_result.get("strengths", [])
    weaknesses = review_result.get("weaknesses", [])
    suggestions = review_result.get("improvement_suggestions", [])
    scores = review_result.get("llm_scores", {})
    
    # 提取原始文档章节
    original_sections = {}
    if original_content:
        original_sections = extract_sections(original_content)
    
    # 构建修订指导
    guidance = "# 修订指南\n\n"
    
    # 添加总体评分和修订目标
    guidance += "## 总体评价\n\n"
    guidance += f"当前研究计划总体评分: {scores.get('总体评分', 'N/A')}/10\n\n"
    
    # 添加优势部分
    if strengths:
        guidance += "## 现有优势 (请保留这些特点)\n\n"
        for i, strength in enumerate(strengths, 1):
            guidance += f"{i}. {strength}\n"
        guidance += "\n"
    
    # 添加主要问题
    if weaknesses:
        guidance += "## 需要改进的关键问题\n\n"
        for i, weakness in enumerate(weaknesses, 1):
            guidance += f"{i}. {weakness}\n"
        guidance += "\n"
    
    # 按章节组织修订建议
    guidance += "## 章节修订指南\n\n"
    
    section_suggestions = {
        "引言": [],
        "文献综述": [],
        "研究设计": [],
        "结论": [],
        "整体结构": []
    }
    
    # 整理按章节的建议
    for sugg in suggestions:
        section = sugg.get("section", "整体结构")
        if section in section_suggestions:
            section_suggestions[section].append({
                "issue": sugg.get("issue", ""),
                "suggestion": sugg.get("suggestion", ""),
                "priority": sugg.get("priority", "中")
            })
    
    # 为每个章节添加修订建议
    for section_name, section_suggs in section_suggestions.items():
        if section_suggs:
            if section_name == "引言":
                key = "introduction"
            elif section_name == "文献综述":
                key = "literature_review"
            elif section_name == "研究设计":
                key = "research_design"
            elif section_name == "结论":
                key = "conclusion"
            else:
                key = None
                
            guidance += f"### {section_name} 修订\n\n"
            
            # 添加原文参考摘要（如果有）
            if key and key in original_sections:
                excerpt = original_sections[key]
                if len(excerpt) > 500:
                    excerpt = excerpt[:500] + "...(省略部分内容)"
                guidance += f"**原文参考**:\n```\n{excerpt}\n```\n\n"
            
            guidance += "**修订建议**:\n"
            for i, sugg in enumerate(section_suggs, 1):
                guidance += f"{i}. 【{sugg['priority']}优先级】{sugg['issue']}\n"
                guidance += f"   改进方向: {sugg['suggestion']}\n\n"
    
    # 评分详情作为参考
    guidance += "## 详细评分参考\n\n"
    for criterion, score in scores.items():
        if criterion != "总体评分":
            guidance += f"- {criterion}: {score}/10\n"
    
    return guidance

def main():
    parser = argparse.ArgumentParser(description="使用评审结果改进研究计划书")
    parser.add_argument("--review", "-r", help="评审结果JSON文件路径", required=True)
    parser.add_argument("--original", "-o", help="原始研究计划书文件路径")
    parser.add_argument("--question", "-q", help="原始研究问题")
    
    args = parser.parse_args()
    
    # 加载评审结果
    review_result = load_review_result(args.review)
    if not review_result:
        print("无法加载评审结果，请检查文件路径")
        return
    
    # 加载原始研究计划（如果提供）
    original_content = None
    if args.original:
        original_content = load_original_proposal(args.original)
        if original_content:
            print(f"已加载原始研究计划: {args.original}")
        else:
            print("警告: 无法加载原始研究计划，将不使用原文进行参考")
    
    # 获取原始研究问题
    research_question = args.question
    if not research_question:
        research_question = review_result.get("research_field", "")
        if not research_question:
            research_question = input("请输入原始研究问题: ")
    
    # 格式化修订指导
    revision_guidance = format_revision_guidance(review_result, original_content)
    print("\n" + "="*60)
    print("修订指南:")
    print(revision_guidance[:500] + "..." if len(revision_guidance) > 500 else revision_guidance)
    print("="*60 + "\n")
    
    # 确认是否继续
    proceed = input("是否使用以上修订指南重新生成研究计划书？(y/n): ")
    if proceed.lower() != 'y':
        print("操作已取消")
        return
    
    print("\n🔄 正在根据评审意见重新生成研究计划...\n")
    
    # 使用原始问题和修订指南生成新的研究计划书
    agent = ProposalAgent()
    result = agent.generate_proposal(research_question, revision_guidance=revision_guidance)
    
    # 处理可能生成的澄清问题
    if result.get("clarification_questions") and not result.get("research_plan"):
        print("\n" + "="*30 + " 需要您进一步澄清 " + "="*30)
        print("为了更好地聚焦研究方向，请回答以下问题：")
        for i, q_text in enumerate(result["clarification_questions"]):
            print(f"{i+1}. {q_text}")
        
        print("\n请将您的回答合并成一段文字输入。")
        user_response = input("您的澄清：")
        user_clarifications = user_response.strip()
        
        print("\n🔄 正在根据您的澄清和评审意见重新规划研究...\n")
        result = agent.generate_proposal(
            research_field=research_question,
            user_clarifications=user_clarifications,
            revision_guidance=revision_guidance
        )
    
    # 输出结果
    print("\n" + "="*60)
    
    if result.get("execution_memory"):
        print(f"执行历史: {len(result['execution_memory'])} 个步骤")
        for memory in result["execution_memory"]:
            print(f"- {memory['description']}: {'成功' if memory['success'] else '失败'}")
    
    # 输出最终报告的保存路径
    if result.get("final_report_markdown") and result["final_report_markdown"] != "报告生成失败":
        output_dir = "./output"
        if os.path.exists(output_dir):
            files = sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True)
            if files:
                latest_report = os.path.join(output_dir, files[0])
                print(f"✅ 改进后的研究计划书已生成并保存到: {latest_report}")
                
                # 提示用户可以进行评估
                print("\n你可以使用以下命令对改进版进行评估:")
                print(f"python review.py --file {latest_report} --field \"{research_question}\"")
    else:
        print("❌ 未能生成改进后的研究计划书。")

if __name__ == "__main__":
    main()