from backend.src.agent.graph import ProposalAgent
import logging 
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ]
)

if __name__ == "__main__":
    # 测试PDF摘要功能
    # pdf_result = summarize_pdf.invoke({"path": "./Papers/test.pdf"})
    # print("PDF摘要测试:", pdf_result)
    
    agent = ProposalAgent()
# <<<<<<< wyy-RAG
#     research_question = "大模型的推理优化"
#     result = agent.generate_proposal(research_question, "demo_test")
=======
    research_question = input("请输入研究问题（Research Question）：")
    
    # 第一次调用，可能生成澄清问题
    result = agent.generate_proposal(research_question，"demo_test")
    
    user_clarifications = ""
    # 检查是否生成了澄清问题且图形在等待输入时结束
    if result.get("clarification_questions") and not result.get("research_plan"): # 通过启发式方法判断：如果存在问题但计划不存在，则图形可能已暂停。
        print("\n" + "="*30 + " 需要您进一步澄清 " + "="*30)
        print("为了更好地聚焦研究方向，请回答以下问题：")
        for i, q_text in enumerate(result["clarification_questions"]):
            print(f"{i+1}. {q_text}")
        
        print("\n请将您的回答合并成一段文字输入。")
        user_response = input("您的澄清：") # 脚本将在这里等待输入
        
        user_clarifications = user_response.strip() # 如果用户直接按回车，这里可以是空的
        
        # 第二次调用，传入用户的澄清（即使为空）
        print("\n🔄 正在根据您的澄清重新规划研究...\n")
        result = agent.generate_proposal(research_question, user_clarifications=user_clarifications)

# >>>>>>> main
    print("\n" + "="*60)
    # print("计划:")
    # print(result["research_plan"])
    print("\n" + "="*60)
    print(f"执行历史: {len(result['execution_memory'])} 个步骤")
    for memory in result["execution_memory"]:
        print(f"- {memory['description']}: {'成功' if memory['success'] else '失败'}")
    print("\n" + "="*60)
    print(f"收集到的论文: {len(result['arxiv_papers'])} 篇")
    print(f"网络搜索结果: {len(result['web_search_results'])} 条")
    print(f"统一参考文献: {len(result['reference_list'])} 条")
    print("\n" + "="*60)
    # print("引言部分:")
    # print(result["introduction"])
    # print("\n" + "="*60)
    # print("文献综述部分:")
    # print(result["literature_review"])
    # print("\n" + "="*60)
    # print("研究设计部分:")
    # print(result["research_design"])
    # print("\n" + "="*60)
    # print("结论部分:") 
    # print(result["conclusion"])
    # print("\n" + "="*60)
    # print("参考文献部分:")
    # print(result["final_references"])

    # 输出最终报告的保存路径或内容
    if result.get("final_report_markdown") and result["final_report_markdown"] != "报告生成失败":
        # 查找报告文件名，因为路径是在函数内部生成的
        output_dir = "./output"
        if os.path.exists(output_dir):
            files = sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True)
            if files:
                latest_report = os.path.join(output_dir, files[0])
                print(f"✅ 最终研究计划书已生成并保存到: {latest_report}")
            else:
                print("✅ 最终研究计划书内容已生成，但未找到具体文件路径。")
        else:
             print("✅ 最终研究计划书内容已生成。")
        # print("\n报告内容预览:\n", result["final_report_markdown"][:1000] + "...") # 可以选择性打印部分内容
    else:
        print("❌ 未能生成最终研究计划书报告。")