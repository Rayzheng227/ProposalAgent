import os
from fastapi import HTTPException
from pathlib import Path

def md_services(research_field: str, uuid: str) -> str:
    file_name = f"Research_Proposal_{research_field}_{uuid}.md"
    # 构建输出文件夹的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(current_dir, '..', '..', 'output')
    # 获取具体的 .md 文件路径
    file_path = os.path.join(output_dir, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return str(file_path)