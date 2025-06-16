from pathlib import Path
from src.agent.graph import ProposalAgent
import os
import subprocess
import logging
from ..entity.stream_mes import StreamMes, StreamClarifyMes, StreamAnswerMes
from ..utils.queue_util import QueueUtil

# 配置logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def agent_service(proposal_id: str, research_question: str):
    logging.info("开始执行agent_service")
    agent = ProposalAgent()
    logging.info("ProposalAgent初始化完成")
    result = agent.generate_proposal(research_question, proposal_id)
    logging.info("=" * 60)
    logging.info(f"执行历史: {len(result['execution_memory'])} 个步骤")
    for memory in result["execution_memory"]:
        logging.info(f"- {memory['description']}: {'成功' if memory['success'] else '失败'}")
    logging.info("=" * 60)
    logging.info(f"收集到的论文: {len(result['arxiv_papers'])} 篇")
    logging.info(f"网络搜索结果: {len(result['web_search_results'])} 条")
    logging.info(f"统一参考文献: {len(result['reference_list'])} 条")
    logging.info("=" * 60)

    # 输出最终报告的保存路径或内容
    if result.get("final_report_markdown") and result["final_report_markdown"] != "报告生成失败":
        # 查找报告文件名，因为路径是在函数内部生成的
        logging.info("查找报告")
        output_dir = Path(__file__).parent.parent.parent.parent / "output"
        if os.path.exists(output_dir):
            files = sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)),
                           reverse=True)
            if files:
                latest_report = os.path.join(output_dir, files[0])
                logging.info(f"✅ 最终研究计划书已生成并保存到: {latest_report}")
                
                # 执行导出脚本
                try:
                    logging.info(f"开始执行导出脚本，提案ID: {proposal_id}")
                    # 获取主目录的路径
                    root_dir = Path(__file__).parent.parent.parent.parent
                    export_script = root_dir / "export2.py"
                    
                    if not export_script.exists():
                        raise FileNotFoundError(f"找不到导出脚本: {export_script}")
                        
                    logging.info(f"使用导出脚本: {export_script}")
                    
                    # 发送开始导出的消息
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=proposal_id,
                        title="开始导出",
                        content="🔄 正在将研究计划书导出为PDF格式",
                        step=100
                    ))
                    
                    # 执行导出脚本
                    logging.info(f"执行命令: uv run {export_script} {latest_report} {proposal_id}")
                    logging.info(f"当前工作目录: {os.getcwd()}")
                    
                    # 检查文件是否存在
                    if not os.path.exists(latest_report):
                        raise FileNotFoundError(f"找不到Markdown文件: {latest_report}")
                    if not os.path.exists(export_script):
                        raise FileNotFoundError(f"找不到导出脚本: {export_script}")
                    
                    # 使用python直接运行脚本，而不是通过uv
                    result = subprocess.run(
                        ["uv","run", str(export_script), latest_report, proposal_id],
                        check=True,
                        capture_output=True,
                        text=True,
                        env=dict(os.environ, PYTHONUNBUFFERED="1")  # 确保Python输出不被缓冲
                    )
                    logging.info("正在使用导出脚本")
                    
                    # 处理输出
                    if result.stdout:
                        logging.info("导出脚本标准输出:")
                        for line in result.stdout.splitlines():
                            logging.info(f"  {line}")
                            # 发送进度消息到前端
                            QueueUtil.push_mes(StreamAnswerMes(
                                proposal_id=proposal_id,
                                title="导出进度",
                                content=line,
                                step=101
                            ))
                    
                    if result.stderr:
                        logging.warning("导出脚本错误输出:")
                        for line in result.stderr.splitlines():
                            logging.warning(f"  {line}")
                            # 发送警告消息到前端
                            QueueUtil.push_mes(StreamAnswerMes(
                                proposal_id=proposal_id,
                                title="导出警告",
                                content=f"⚠️ {line}",
                                step=101
                            ))
                    
                    # 发送完成消息
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=proposal_id,
                        title="导出完成",
                        content="✅ PDF导出完成",
                        step=102,
                        is_finish=True
                    ))
                    
                    logging.info("导出脚本执行成功")
                    
                except subprocess.CalledProcessError as e:
                    error_msg = f"执行导出脚本失败: {e}\n错误输出: {e.stderr}"
                    logging.error(error_msg)
                    # 发送错误消息到前端
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=proposal_id,
                        title="导出失败",
                        content=f"❌ {error_msg}",
                        step=103,
                        is_finish=True
                    ))
                    raise Exception(f"导出失败: {e.stderr}")
                except Exception as e:
                    error_msg = f"执行导出脚本时发生未知错误: {e}"
                    logging.error(error_msg)
                    # 发送错误消息到前端
                    QueueUtil.push_mes(StreamAnswerMes(
                        proposal_id=proposal_id,
                        title="导出失败",
                        content=f"❌ {error_msg}",
                        step=103,
                        is_finish=True
                    ))
                    raise Exception(f"导出失败: {str(e)}")
            else:
                logging.info("✅ 最终研究计划书内容已生成，但未找到具体文件路径。")
        else:
            logging.info("✅ 最终研究计划书内容已生成。")
    else:
        logging.error("❌ 未能生成最终研究计划书报告。")
