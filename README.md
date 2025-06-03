# ProposalAgent
A Proposal Agent for Advanced AI Course in HIAS
# Team Member
郑锐、谢秋云、樊彬峰、禚宣伟、吴业阳

----
# 初步计划
## 项目简介
Proposal‑Agent 是一套用于 **自动生成并迭代优化科研计划书（Research Proposal）** 的多智能体系统。  
用户仅需输入 **研究领域 / 方向**，系统即会：

1. 检索最新文献与公开数据；
2. 产出包含 **研究背景、目标、方法、时间规划、预期成果** 等要素的完整 Proposal（PDF 形式导出）；
3. 通过 Reviewer‑Agent 按多维指标打分并给出改进意见，自动迭代直至平均得分达到设定阈值。

----
# 以下是临时记录一些东西的地方

## 大致流程

输入研究领域和方向————>允许参考案例(在Arxiv、github、Google Scholar上等内容）——>分步骤生成文本——>转换为文档

可视化界面(Web UI)

搜索：tavily API


## 问题

如何判断输出结果好坏？
工具调用：哪些需要调用？

## 任务分工

Agent框架(Langchain\Langgraph)————> 郑

==RAG参考文本==、Web UI ————> 谢

## arxiv的调用
```python
import arxiv
 
# 构建默认的API客户端。
client = arxiv.Client()
 
# 搜索关键词为 "quantum" 的最新的10篇文章。
search = arxiv.Search(
  query="quantum",
  max_results=10,
  sort_by=arxiv.SortCriterion.SubmittedDate
)
 
results = client.results(search)
 
# `results` 是一个生成器；你可以逐个遍历其元素...
for r in client.results(search):
  print(r.title)
# ...或者将其全部转换为列表。注意：对于大型结果集，这可能会很慢。
all_results = list(results)
print([r.title for r in all_results])
 
# 有关高级查询语法的文档，请参阅arXiv API用户手册：
# https://arxiv.org/help/api/user-manual#query_details
search = arxiv.Search(query="au:del_maestro AND ti:checkerboard")
first_result = next(client.results(search))
print(first_result)
 
# 搜索ID为 "1605.08386v1" 的论文
search_by_id = arxiv.Search(id_list=["1605.08386v1"])
# 重用客户端以获取论文，然后打印其标题。
first_result = next(client.results(search))
print(first_result.t
```
##  Tavily Search的调用
```python
from langchain_community.tools import TavilySearchResults

tool = TavilySearchResults(
    max_results=5,
    search_depth="advanced",
    include_answer=True,
    include_raw_content=True,
    include_images=True,
)


result = tool.invoke({"query": "What happened at the last wimbledon"})

for item in result:
    print(f"URL: {item['url']}")
    print(f"Content: {item['content']}\n")

```
  



