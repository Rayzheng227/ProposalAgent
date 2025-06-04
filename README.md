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
3. 运行简单的DEMO
```
uv run agent.py
```
4. 若后续开发有增加所需的库等操作，执行`uv add xxx`，如`uv add numpy`，会自动在`pyproject.toml`中以及`.venv`中增加相关库

----

# 写给队友看的一些临时的想法

1. pdf/其他格式导出的部分 ————————————>str(由md组成)
2. **加入Reviewer相关部分**————接收人类标注的结果(结构、内容)
3. 前端webui,可参考
4. (maybe)加入中间的反思
5. 加入其他搜索源

## How to use it?
【2025.6.4】 重构了一下代码，让他更模块化了；
- `/backend/src/agent/graph.py` ：这个部分是整体的Langgraph框架
- `/backend/src/agent/state.py` ：这一部分存储框架所需要的属性，如：在框架中增加了中间输出，则也需要到state中增加
- `/backend/src/agent/tools.py` : 这一部分存储的是Proposal Agent本身需要去使用的工具，若工具有变动，记得修改同目录下的tools.json
- `agent.py` ： 一个简单的DEMO，演示如何去通过ProposalAgent生成一个完整的Proposal
- `output` : 存储导出的markdown文件
- `Papers` : 存储Agent中途从Arxiv下载的论文，在概括文章时需要
- `backend` ：整体存储整个后端的内容
- `frontend` : 包含前端信息


比如说，想要输出pdf的结果更好，如：**针对Proposal的时间线**，写了一个绘图的可视化工具，可以先通过`@tools`装饰器在`tools.py`中加入新函数，再在需要用到的图的节点中加入相关说明，即可让Agent在对应阶段能够去调用该工具。

## 目前已知的一些不足：
1. ***搜索策略、搜索源问题***：Arxiv的搜索策略有一些不足，我运行了几次发现老是搜索到同一批文件(明明搜索的关键词不一样)；或许可以：**改善搜索策略**、**增加搜索源**(并不是所有论文在Arxiv上都有对应预印本；我之前加入了一个CrossRef，在网上看到说是他不需要注册API，但是我自己用的时候偶尔会出错)；
2.***输出问题***：*最终输出pdf的部分有问题(我已经写了一个export.py)，目标是将markdown文件转化为pdf，但是在中文显示、整体布局等上面有问题，可以整体去修改，目标是：读取`output`文件夹下的md文件，转化为pdf(或是其他更好阅读的格式)。这一方面可以参考`WeasyPrint`这一个库，据说是能将html文件转化为pdf，效果会更好看；或者说你有其他办法能够最终生成一个`更好阅读的格式`（word、pdf、ppt等都可以）
3. ***可视化问题***：如上所述，整体最后的输出结果缺乏一些图片等，这会显得我们的Proposal有点小小的尴尬，也许可以加入一些其他的内容(反正就是让整体Proposal更好看一点)
4. ***前端相关***构建前端，即WebUI相关，可以参考:[这里](https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart.git)，这个仓库的frontend部分提供了一个我看着感觉很高级的webUI，所有的中间输出相关，基本上都在`Graph.py`中，中间输出内容基本上以`logging.info`为主，可以捕获这些输出去做前端。
5. ***Reviewer—强化输出***按照我们讨论的，可以加入一个Reviewer，去对我们生成的Proposal进行评分，然后返回给ProposalAgent进行改善
6. ***工作量上***(或者说，涉及的知识点范围），若要涉及到更多的现有技术，可以考虑**MCP**,**RAG**；其中MCP相关的内容是作为tools的一部分；比如说：如果有对应的生成、修改最终格式的MCP，那应该是挺不错的； **RAG**上，我思考了一下可以加入到数据库的内容，比如说,我前面提到的**搜索策略**问题，我发现，在有些情况下，Agent对专业词汇的理解不够，而且有些方面的论文，**可能在标题、关键词中没有相关的内容**，但整体的文章是关于这个方向的，这种情况下我们的搜索策略就无法搜索到对应的关键词。
7. ***反思功能***：这个可能我后面有时间自己会增加，目前的整体规划是：若网络上、Arxiv等搜索到的相关内容不超过3个，则重新搜索；但是这个方法是显然不足的，我想的一个方式是：让LLM去判断，目前收集到的资料**是否足以他了解完整的行业趋势**，将最终结果限定为一个Bool型，若为真，则截止搜索工作；若不足，则继续搜索工作。或者也许你能想到更好的策略。
8. ***记忆管理问题***：目前没有提供一些记忆管理策略，这样会造成每次的token数很高，这在成本上是一个挑战；也许可以考虑去优化这方面的策略

## 开发注意事项

希望最好能够每个功能部分pull新的分支，以免影响整体


---

希望能够完善一下上面所述的不足!!! 




