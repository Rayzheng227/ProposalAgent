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

## Feature
- 🔍 引入多源学术数据库检索（ArXiv / IEEE Xplore）
- 🤖 Reviewer‑Agent RLHF 强化
- 	🌐 支持多语言 Proposal 输出

# Requirements
- `python>=3.10`
- `uv`: Install uv as python project manager from [here](https://github.com/astral-sh/uv)

# Installation
1. Clone the repository
```bash
git clone https://github.com/Rayzheng227/ProposalAgent.git
cd ProposalAgent
```
2. Sync virtual enviroment by uv
```
uv sync
```
3. RUNNNN
```
uv run agent.py
```
4. 若后续开发有增加所需的库等操作，执行`uv add xxx`，如`uv add numpy`，会自动在`pyproject.toml`中以及`.venv`中增加相关库

----

# 以下是临时记录一些东西的地方

1. pdf/其他格式导出的部分 ————————————>str(由md组成)
2. 加入Reviewer相关部分————接收人类标注的结果(结构、内容)
3. 前端webui,可参考[这里](https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart.git)

  



