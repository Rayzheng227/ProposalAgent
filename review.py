from backend.src.reviewer.reviewer import ReviewerAgent
import os
import logging
import json
import argparse
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ]
)

def load_proposal_from_file(file_path):
    """从文件加载研究计划书内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logging.error(f"加载文件失败: {e}")
        return None

def save_review_result(result, output_dir="output/reviews"):
    """保存评审结果到文件"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"review_result_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return filepath

def main():
    parser = argparse.ArgumentParser(description="研究计划书评审工具")
    parser.add_argument("--file", "-f", help="要评审的研究计划书文件路径")
    parser.add_argument("--section", "-s", help="要评审的特定章节 (引言/文献综述/研究设计/结论)")
    parser.add_argument("--field", "-r", default="通用研究", help="研究领域")
    
    args = parser.parse_args()
    
    if not args.file:
        print("请指定要评审的文件路径。使用 --file 参数。")
        return
    
    # 初始化评审代理
    reviewer = ReviewerAgent()
    
    # 加载研究计划书
    proposal_content = load_proposal_from_file(args.file)
    if not proposal_content:
        print(f"无法加载文件: {args.file}")
        return
    
    print(f"\n{'-'*40}\n评审开始\n{'-'*40}")
    
    if args.section:
        # 评审特定章节
        section_name = args.section
        print(f"正在评审 '{section_name}' 章节...")
        result = reviewer.review_section(proposal_content, section_name, args.field)
    else:
        # 评审整个研究计划书
        print(f"正在评审完整研究计划书...")
        result = reviewer.review_proposal(proposal_content, args.field)
    
    if result.get("success"):
        # 保存评审结果
        output_file = save_review_result(result)
        print(f"\n评审完成! 结果已保存到: {output_file}")
        
        # 显示评分结果
        print("\n评分结果:")
        scores = result.get("llm_scores", {})
        for criterion, score in scores.items():
            print(f"- {criterion}: {score}")
        
        # 显示主要建议
        print("\n主要改进建议:")
        for i, suggestion in enumerate(result.get("improvement_suggestions", [])[:3], 1):
            print(f"{i}. {suggestion.get('suggestion', '无具体建议')}")
        
        if len(result.get("improvement_suggestions", [])) > 3:
            print(f"... 还有 {len(result.get('improvement_suggestions', [])) - 3} 条建议 ...")
    else:
        print(f"\n评审失败: {result.get('error', '未知错误')}")

if __name__ == "__main__":
    main()