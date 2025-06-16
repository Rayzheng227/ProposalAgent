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
    logging.info(f"执行命令: uv run {export_script} {latest_report} {proposal_id}")
    logging.info(f"当前工作目录: {os.getcwd()}")
    logging.info("正在执行导出脚本")
    
    try:
        process = subprocess.Popen(
            [sys.executable, export_script, latest_report, proposal_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, 'EDITOR': 'none'}  # 防止自动打开文件
        )
        
        # 实时读取输出
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                output = output.strip()
                if output.startswith("QUEUE_MESSAGE:"):
                    try:
                        message = json.loads(output[len("QUEUE_MESSAGE:"):])
                        QueueUtil.push_mes(StreamAnswerMes(**message))
                    except json.JSONDecodeError:
                        logging.error(f"无法解析QUEUE_MESSAGE: {output}")
                else:
                    logging.info(output)
                
        # 检查是否有错误
        stderr_output = process.stderr.read()
        if stderr_output:
            logging.error(f"导出脚本错误输出: {stderr_output}")
            
        # 等待进程完成
        return_code = process.wait()
        if return_code != 0:
            raise Exception(f"导出脚本执行失败，返回码: {return_code}")
        
        logging.info("导出脚本执行完成")
        return True
        
    except Exception as e:
        logging.error(f"执行导出脚本时发生错误: {str(e)}")
        raise
