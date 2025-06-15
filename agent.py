from backend.src.agent.graph import ProposalAgent
import logging 
import os
import uuid
import signal
from contextlib import contextmanager
from datetime import datetime


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ],
    force=True # 强制覆盖任何已存在的配置
)


@contextmanager
def timeout_input(timeout_seconds):
    """带超时的输入上下文管理器"""
    def timeout_handler(signum, frame):
        raise TimeoutError("输入超时")
    
    # 设置超时信号
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)
    
    try:
        yield
    finally:
        signal.alarm(0)  # 取消超时

if __name__ == "__main__":
    agent = ProposalAgent()
    research_question = input("请输入研究问题（Research Question）：")
    proposal_id = f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    # 第一次调用，可能生成澄清问题
    result = agent.generate_proposal(research_question, proposal_id)
    user_clarifications = ""
    # 检查是否生成了澄清问题且图形在等待输入时结束
    # if result.get("clarification_questions") and not result.get("research_plan"): # 通过启发式方法判断：如果存在问题但计划不存在，则图形可能已暂停。
    #     print("\n" + "="*30 + " 需要您进一步澄清 " + "="*30)
    #     print("为了更好地聚焦研究方向，请回答以下问题：")
    #     for i, q_text in enumerate(result["clarification_questions"]):
    #         print(f"{i+1}. {q_text}")
        
    #     print("\n请将您的回答合并成一段文字输入。")
    #     try:
    #         with timeout_input(60):  # 10秒超时
    #             user_response = input("您的澄清：") # 脚本将在这里等待输入
    #             user_clarifications = user_response.strip() # 如果用户直接按回车，这里可以是空的
    #     except TimeoutError:
    #         print("\n⏰ 输入超时，将使用默认设置继续...")
    #         user_clarifications = "None"
    #     except KeyboardInterrupt:
    #         print("\n用户取消输入，将使用默认设置继续...")
    #         user_clarifications = "None"

    #     # 第二次调用，传入用户的澄清（即使为空）
    #     print("\n🔄 正在根据您的澄清重新规划研究...\n")
    #     result = agent.generate_proposal(research_question, user_clarifications=user_clarifications, proposal_id=proposal_id)

    if result.get("final_report_markdown") and result["final_report_markdown"] != "报告生成失败":
        output_dir = "./output"
        if os.path.exists(output_dir):
            files = sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True)
            if files:
                latest_report = os.path.join(output_dir, files[0])
                logging.info(f"✅ 最终研究计划书已生成并保存到: {latest_report}")
                
                # 生成 PDF
                try:
                    logging.info("🔄 正在生成 PDF 文件...")
                    import subprocess
                    result = subprocess.run(['uv', 'run', 'export2.py', latest_report], 
                                         capture_output=True, 
                                         text=True, 
                                         check=True)
                    logging.info("✅ PDF 文件生成成功！")
                    # 查找生成的 PDF 文件
                    pdf_dir = "./exporter/pdf_output"
                    if os.path.exists(pdf_dir):
                        pdf_files = sorted(os.listdir(pdf_dir), 
                                        key=lambda x: os.path.getmtime(os.path.join(pdf_dir, x)), 
                                        reverse=True)
                        if pdf_files:
                            latest_pdf = os.path.join(pdf_dir, pdf_files[0])
                            logging.info(f"📄 PDF 文件位置: {latest_pdf}")
                            # 尝试自动打开 PDF
                            try:
                                import platform
                                if platform.system() == "Linux":
                                    subprocess.run(['xdg-open', latest_pdf], check=False)
                                elif platform.system() == "Darwin":
                                    subprocess.run(['open', latest_pdf], check=False)
                                elif platform.system() == "Windows":
                                    subprocess.run(['start', latest_pdf], shell=True, check=False)
                            except Exception as e:
                                logging.warning(f"无法自动打开 PDF 文件: {e}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"❌ PDF 生成失败: {e}")
                    logging.error(f"错误输出: {e.stderr}")
                except Exception as e:
                    logging.error(f"❌ PDF 生成过程中发生错误: {e}")
            else:
                logging.info("✅ 最终研究计划书内容已生成，但未找到具体文件路径。")
        else:
            logging.info("✅ 最终研究计划书内容已生成。")
    else:
        logging.error("❌ 未能生成最终研究计划书报告。")