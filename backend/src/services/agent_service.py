from pathlib import Path

from src.agent.graph import ProposalAgent
import os


def agent_service(proposal_id: str, research_question: str):
    # 测试PDF摘要功能
    # pdf_result = summarize_pdf.invoke({"path": "./papers/test.pdf"})
    # print("PDF摘要测试:", pdf_result)
    agent = ProposalAgent()
    result = agent.generate_proposal(research_question, proposal_id)
    print("\n" + "=" * 60)
    # print("计划:")
    # print(result["research_plan"])
    print("\n" + "=" * 60)
    print(f"执行历史: {len(result['execution_memory'])} 个步骤")
    for memory in result["execution_memory"]:
        print(f"- {memory['description']}: {'成功' if memory['success'] else '失败'}")
    print("\n" + "=" * 60)
    print(f"收集到的论文: {len(result['arxiv_papers'])} 篇")
    print(f"网络搜索结果: {len(result['web_search_results'])} 条")
    print(f"统一参考文献: {len(result['reference_list'])} 条")
    print("\n" + "=" * 60)
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
        output_dir = Path(__file__).parent.parent.parent.parent / "output"
        if os.path.exists(output_dir):
            files = sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)),
                           reverse=True)
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
