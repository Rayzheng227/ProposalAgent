import os
from fastapi import HTTPException
from pathlib import Path

def md_services(research_field: str, uuid: str) -> str:
    # 获取当前文件的绝对路径
    current_file_path = Path(__file__).resolve()
    # 获取项目的根目录路径
    project_root = current_file_path.parents[1]  # 因为 start.py 在 ProposalAgent/backend/src/agent/routers 下
    file_name = f"Research_Proposal_{research_field}_{uuid}.md"
    # 构建输出文件夹的绝对路径
    output_dir = project_root / 'routers/output'
    # 获取具体的 .md 文件路径
    file_path = output_dir / file_name
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return str(file_path)