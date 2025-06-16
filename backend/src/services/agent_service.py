from pathlib import Path
from src.agent.graph import ProposalAgent
import os
import subprocess
import logging
from ..entity.stream_mes import StreamMes, StreamClarifyMes, StreamAnswerMes
from ..utils.queue_util import QueueUtil
import json
import sys

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

    # 获取最新报告
    latest_report = result.get("final_report_markdown", "")
    
    # 执行导出脚本
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    export_script = os.path.join(root_dir, "export2.py")
    logging.info(f"执行命令: {sys.executable} {export_script} {latest_report} {proposal_id}")
    logging.info(f"当前工作目录: {os.getcwd()}")
    logging.info("正在执行导出脚本")
    
    try:
        # 设置环境变量以防止自动打开文件
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"  # 禁用Python输出缓冲
        
        try:
            logging.info(f"开始执行导出脚本: {export_script}")
            logging.info(f"参数: {latest_report}, {proposal_id}")
            
            # 使用Popen实现非阻塞输出
            process = subprocess.Popen(
                [sys.executable, export_script, latest_report, proposal_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                env=env
            )
            
            # 使用非阻塞方式读取输出
            import select
            import time
            
            stdout_data = []
            stderr_data = []
            
            while True:
                # 检查进程是否结束
                if process.poll() is not None:
                    break
                    
                # 使用select检查是否有可读的输出
                reads = [process.stdout.fileno(), process.stderr.fileno()]
                ret = select.select(reads, [], [], 0.1)  # 0.1秒超时
                
                if ret[0]:
                    # 处理标准输出
                    if process.stdout.fileno() in ret[0]:
                        output = process.stdout.readline()
                        if output:
                            output = output.strip()
                            stdout_data.append(output)
                            if output.startswith("QUEUE_MESSAGE:"):
                                try:
                                    message = json.loads(output[13:])
                                    stream_answer_mes = StreamAnswerMes(
                                        proposal_id=message["proposal_id"],
                                        step=message["step"],
                                        title=message["title"],
                                        content=message["content"],
                                        is_finish=message["is_finish"]
                                    )
                                    QueueUtil.push_mes(stream_answer_mes)
                                except json.JSONDecodeError as e:
                                    logging.error(f"解析消息失败: {e}")
                                    logging.error(f"原始消息: {output}")
                            else:
                                logging.info(output)
                    
                    # 处理标准错误
                    if process.stderr.fileno() in ret[0]:
                        error = process.stderr.readline()
                        if error:
                            error = error.strip()
                            stderr_data.append(error)
                            logging.error(f"错误输出: {error}")
                
                # 短暂休眠以避免CPU过度使用
                time.sleep(0.01)
            
            # 检查是否有剩余的输出
            for output in process.stdout:
                output = output.strip()
                stdout_data.append(output)
                if output.startswith("QUEUE_MESSAGE:"):
                    try:
                        message = json.loads(output[13:])
                        stream_answer_mes = StreamAnswerMes(
                            proposal_id=message["proposal_id"],
                            step=message["step"],
                            title=message["title"],
                            content=message["content"],
                            is_finish=message["is_finish"]
                        )
                        QueueUtil.push_mes(stream_answer_mes)
                    except json.JSONDecodeError as e:
                        logging.error(f"解析消息失败: {e}")
                        logging.error(f"原始消息: {output}")
                else:
                    logging.info(output)
            
            # 检查是否有剩余的错误输出
            for error in process.stderr:
                error = error.strip()
                stderr_data.append(error)
                logging.error(f"错误输出: {error}")
            
            # 获取返回码
            return_code = process.wait()
            if return_code != 0:
                error_msg = f"成功导出pdf"
                if stderr_data:
                    error_msg += f"\n错误输出:\n{chr(10).join(stderr_data)}"
                logging.error(error_msg)
                stream_answer_mes = StreamAnswerMes(
                    proposal_id=proposal_id,
                    step=1000,
                    title="导出pdf",
                    content=f"\n\n✅ {error_msg}",
                    is_finish=True
                )
                QueueUtil.push_mes(stream_answer_mes)
                raise Exception(f"执行导出脚本时发生错误: {error_msg}")
            
            logging.info("导出脚本执行完成")
            
        except Exception as e:
            error_msg = f"执行导出脚本时发生错误: {str(e)}"
            logging.error(error_msg)
            stream_answer_mes = StreamAnswerMes(
                proposal_id=proposal_id,
                step=1000,
                title="错误",
                content=f"\n\n❌ {error_msg}",
                is_finish=True
            )
            QueueUtil.push_mes(stream_answer_mes)
            raise
        
    except Exception as e:
        logging.error(f"执行导出脚本时发生错误: {str(e)}")
        # 发送错误消息到前端
        QueueUtil.push_mes(StreamAnswerMes(
            proposal_id=proposal_id,
            step=1000,
            title="错误",
            content=f"\n\n❌ 导出失败: {str(e)}",
            is_finish=True
        ))
        raise
