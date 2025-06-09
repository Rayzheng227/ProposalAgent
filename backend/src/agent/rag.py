from langchain_openai import ChatOpenAI
import os
from langchain_core.messages import HumanMessage, SystemMessage
from typing import List
from dotenv import load_dotenv

load_dotenv()
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")


def generate_search_queries(prompt: str) -> str:
    """
    利用 LLM 生成多个高质量的 ArXiv 搜索关键词

    Args:
        prompt: 用户输入的自然语言提示词，如“大模型优化”
        llm_client: 一个 LangChain 兼容的 LLM 实例（如 ChatOpenAI）

    Returns:
        List[str]: 适合 ArXiv 搜索的英文关键词列表
    """
    system_prompt = """你是一个专业的学术研究助手，擅长将中文提示词转换为适合在 ArXiv 上使用的英文搜索关键词。
请根据用户输入的提示词，生成5个英文关键词或短语，用于在 ArXiv 上进行学术论文搜索。
要求：
- 关键词要尽可能涵盖用户意图的不同方面
- 包括技术术语、近义词、专业表达等
- 不需要解释，只需返回关键词列表，每个一行
- 关键词按与中文提示词的相关性排序
"""
    llm = ChatOpenAI(
        api_key=DASHSCOPE_API_KEY,
        model="qwen-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0
    )

    user_input = f"请为以下主题生成搜索关键词：{prompt}"

    # 使用 LangChain 支持的消息格式
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ]

    # 调用 LLM
    response = llm.invoke(messages)

    # 提取内容并按行分割
    content = response.content
    # queries = [line.strip() for line in content.split('\n') if line.strip()]

    return content


if __name__ == "__main__":
    queries = generate_search_queries("大模型的推理优化")
    print(queries)
