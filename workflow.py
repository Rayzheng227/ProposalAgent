from backend.src.agent.graph import ProposalAgent
from backend.src.reviewer.reviewer import ReviewerAgent
import os
import logging
import json
import argparse
from datetime import datetime
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ]
)

def save_to_file(content, filename, output_dir="output"):
    """保存内容到文件"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

def run_proposal_generation_review_workflow(research_question, max_iterations=3):
    """运行完整的提案生成-评审-改进工作流"""
    proposal_agent = ProposalAgent()
    reviewer_agent = ReviewerAgent()
    
    print(f"📝 开始研究主题: '{research_question}'")
    
    # 第一次生成
    print("\n[第1轮] 初始研究计划生成中...")
    result = proposal_agent.generate_proposal(research_question)
    
    # 处理澄清问题
    if result.get("clarification_questions") and not result.get("research_plan"):
        print("\n需要澄清以下问题:")
        for i, q in enumerate(result["clarification_questions"], 1):
            print(f"{i}. {q}")
        
        user_clarifications = input("\n请提供澄清 (或按Enter跳过): ")
        result = proposal_agent.generate_proposal(research_question, user_clarifications=user_clarifications)
    
    # 记录迭代历史
    iterations = []
    
    # 迭代改进
    for iteration in range(max_iterations):
        # 保存当前版本
        if result.get("final_report_markdown"):
            current_report = result["final_report_markdown"]
            version_file = save_to_file(
                current_report,
                f"proposal_v{iteration+1}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                "output/iterations"
            )
            print(f"\n当前版本已保存: {version_file}")
        else:
            print("\n未能获取完整报告内容，跳过保存")
            break
        
        if iteration >= max_iterations - 1:
            break  # 最后一轮不再评审
            
        # 评审当前版本
        print(f"\n[第{iteration+1}轮] 评审进行中...")
        review_result = reviewer_agent.review_proposal(current_report, research_question)
        
        if not review_result.get("success"):
            print(f"评审失败: {review_result.get('error', '未知错误')}")
            break
            
        # 生成修订指导
        print("生成修订建议中...")
        guidance_result = reviewer_agent.generate_revision_guidance(
            review_result, research_question
        )
        
        # 记录这一轮的结果
        iterations.append({
            "iteration": iteration + 1,
            "scores": review_result.get("llm_scores", {}),
            "strengths": review_result.get("strengths", []),
            "weaknesses": review_result.get("weaknesses", [])
        })
        
        # 显示分数
        print("\n评分结果:")
        scores = review_result.get("llm_scores", {})
        for criterion, score in scores.items():
            print(f"- {criterion}: {score}")
            
        # 根据修订指导改进
        print(f"\n[第{iteration+2}轮] 根据评审意见改进中...")
        
        # 这里可以添加逻辑将修订指导转换为ProposalAgent可理解的格式
        # 目前简单地将主要修订点作为额外输入传递
        
        revision_instructions = guidance_result.get("revision_instructions", [])
        if revision_instructions:
            revision_text = "修订要点:\n" + "\n".join([
                f"- {item.get('specific_instruction', '')}" 
                for item in revision_instructions[:3]
            ])
            
            # 将评审意见作为额外输入传给ProposalAgent
            # 这里需要ProposalAgent支持接收revision_guidance参数
            # result = proposal_agent.generate_proposal(research_question, revision_guidance=revision_text)
            
            # 暂时打印出来，需要后续实现ProposalAgent接收修订指南的功能
            print("\n需要传递给ProposalAgent的修订指南:")
            print(revision_text)
            time.sleep(2)  # 模拟处理时间
            
    # 保存迭代历史
    if iterations:
        history_file = save_to_file(
            json.dumps(iterations, ensure_ascii=False, indent=2),
            f"iteration_history_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            "output/history"
        )
        print(f"\n迭代历史已保存: {history_file}")
    
    return result

def main():
    parser = argparse.ArgumentParser(description="研究计划生成评审工作流")
    parser.add_argument("--topic", "-t", help="研究主题")
    parser.add_argument("--iterations", "-i", type=int, default=2, help="最大迭代次数")
    
    args = parser.parse_args()
    
    if not args.topic:
        args.topic = input("请输入研究主题: ")
    
    run_proposal_generation_review_workflow(args.topic, args.iterations)

if __name__ == "__main__":
    main()