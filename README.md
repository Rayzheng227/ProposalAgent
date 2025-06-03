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

# 大致流程

输入研究领域和方向————>允许参考案例(在Arxiv、github、Google Scholar上等内容）——>分步骤生成文本——>转换为文档

可视化界面(Web UI)

搜索：tavily API


# 问题

如何判断输出结果好坏？
工具调用：哪些需要调用？

# 任务分工

Agent框架(Langchain\Langgraph)————> 郑

==RAG参考文本==、Web UI ————> 谢

联网搜索功能实现 ————>


