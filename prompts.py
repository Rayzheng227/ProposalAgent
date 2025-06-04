"""
存储所有的Prompt instructions
"""
from datetime import datetime


master_plan_instruction = """
You are a senior research expert and project planner. The user has proposed a research topic or question: "{research_field}".

You are equipped with the following tools you can call during task execution:
{tools_info}

Your goal is **not** to generate the full research proposal directly.  
Instead, your task is to design a **master-level planning strategy** for how to **create** a comprehensive research proposal.

Please break down the research proposal into its standard components:
1. Introduction (problem background, significance, research gap)
2. Literature Review (what to search, which papers to read)
3. Project Design (research objectives, methodology, technical roadmap)
4. Timeline (phase-based work plan)
5. Expected Outcomes (what results and deliverables are expected)

---

## 🔍 Your output should be a task-oriented, tool-driven plan including:
- **What needs to be done** in each proposal section
- **Which tools or strategies** to use (e.g., search ArXiv, use web search, summarize prior research)
- **What keywords or topics** to search
- **What kind of materials** to collect or analyze
- A step-by-step breakdown of what the Agent should do

Please provide the plan in a structured Markdown format, with numbered sections for each major task.
Include a brief description and expected outcome for each step.

Focus on **execution planning**, not on writing content directly.
Ensure the steps are concrete, actionable, and make full use of the available tools.
...

"""

EXECUTION_PLAN_PROMPT = """
You are a senior research expert and scientific retrieval strategist.

The user is exploring the research domain: "{research_field}"  
They have already generated a preliminary research plan as follows:

----------------------------
📘 Research Plan:
{research_plan}
----------------------------

You also have access to the following tools for executing tasks:
{tools_info}

{memory_text}

---

🎯 Your Task:
Based on the above research plan **and** the execution history, your goal is to **propose the next concrete execution steps**.

Each step should be:
- **Specific**: describe what to do and why
- **Actionable**: can be performed using the available tools
- **Non-redundant**: avoid repeating failed or already completed tasks
- **Strategic**: prioritize steps that help advance the research plan meaningfully

**Available Actions:**
- `search_arxiv_papers`: Search and download ArXiv papers
- `search_web_content`: Search web content using Tavily
- `search_crossref_papers`: Search academic papers via CrossRef
- `summarize_pdf`: Summarize downloaded PDF files (use this for important papers after downloading)

**Strategy for PDF Analysis:**
1. First search and download relevant papers using arxiv or crossref tools
2. For the most important/relevant papers, use summarize_pdf to get detailed analysis
3. Use the PDF path from the download results (usually in "./Papers/" directory)

Please return your output in the following **strict JSON format**:

```json
{{
  "steps": [
    {{
      "step_id": 1,
      "action": "search_arxiv_papers",
      "parameters": {{"query": "example keyword", "max_results": 5}},
      "description": "Search ArXiv for recent papers on X",
      "expected_outcome": "Find recent academic literature related to topic X"
    }},
    {{
      "step_id": 2,
      "action": "summarize_pdf",
      "parameters": {{"path": "./Papers/2025.12345v1_Example_Paper.pdf"}},
      "description": "Summarize the most relevant downloaded paper",
      "expected_outcome": "Get detailed analysis of key research findings"
    }}
  ]
}}
```

**Note**: When using summarize_pdf, ensure the PDF path corresponds to a file that was actually downloaded in previous steps.
"""


proposal_introduction_instruction = """
You are tasked with drafting the **Introduction section** of a Research Proposal. Your goal is to clearly present the research topic, explain its importance, and formulate well-defined research questions based on a recognized research gap.

The target audience is **academic readers who may not be experts** in the specific domain, so clarity, structure, and depth of explanation are essential.

---

## 🎯 Output Instructions

Please generate a well-structured academic-style text of **at least 600 words** in **Chinese**, covering the following sections:

---

## 1. Research Topic Introduction

- Introduce the research topic in a way that is accessible to an informed academic audience outside the specific domain.
- Provide essential **background information**:
  - Key historical developments,
  - Major milestones,
  - Emerging trends and recent advances in the field.

---

## 2. Significance

- Explain **why this topic matters** to you as a researcher.
- Justify **why others should care** (academics, practitioners, or society at large).
- Refer to how other scholars have framed its importance and share your **own perspective** on its significance.
- Highlight what makes this topic **timely, relevant, or urgent**.

---

## 3. From Research Gap to Research Question

- Identify a **research gap** based on existing academic literature.
- Explain **why** this gap is worth exploring.
- Mention any **key problems, concepts, or theoretical developments** that are relevant to this gap.
- Use this gap to formulate **a clear, focused research question (or multiple related questions)**.

### ✍️ Criteria for a Strong Research Question:

- **Relevant**: Directly addresses a problem within the research field.
- **Important**: Engages with central debates or unresolved issues.
- **Clear**: Written in unambiguous and precise language.
- **Precise**: Well-defined scope and subject.
- **Researchable**: Feasible with accessible data and methods.

### 💡 Expression Guidelines:

- Prefer **"How"** or **"Why"** questions to encourage analytical thinking.
- Avoid leading or biased language.
- Incorporate key concepts and potential relationships in the phrasing.
- Ensure questions are open-ended and allow for multiple possible answers.

---

## 🧩 Final Objective

The output should serve as a compelling **opening section of a research proposal**, making a clear case for:
- What the research is about,
- Why it matters,
- What exact question(s) it aims to address.

Use formal academic tone and cite hypothetical or known examples where appropriate.

**Important Note**: This section should focus *only* on the introduction, significance, and research questions. **Do not include** timelines, expected outcomes, or a general summary of the entire proposal, as these will be covered in a separate "Conclusion" section.
"""

LITERATURE_REVIEW_PROMPT = """
You are an academic researcher specializing in literature analysis and synthesis.

The user is preparing a **research proposal** in the field of:
**"{research_field}"**

You have access to relevant literature sources (e.g., ArXiv, Google Scholar, databases) and tools to search and retrieve papers.

---

🎯 Your task is to **write the literature review section** of the proposal.  
This is not a comprehensive list of all sources, but a focused and well-structured synthesis of the **most relevant and recent** research related to the topic.

**IMPORTANT**: You will be provided with the **already written Introduction section**. Your literature review should:
- **Build upon** the research questions and gaps identified in the Introduction
- **Avoid repeating** content already covered in the Introduction
- **Provide deeper analysis** of the literature that supports the research rationale
- **Maintain coherence** with the research direction established in the Introduction

---

## ✍️ Guidelines for Writing:

### 1. Purpose
The literature review should:
- **Expand** on the literature briefly mentioned in the Introduction with deeper analysis
- Provide **systematic categorization** of research approaches, methodologies, and findings
- Highlight **detailed trends, schools of thought, and theoretical frameworks**
- Identify **specific gaps, contradictions, or limitations** in existing research
- **Justify the proposed research** by connecting it to unresolved problems identified in the Introduction

### 2. Focus
- Concentrate on **works directly related** to the research questions posed in the Introduction
- Emphasize **influential and recent** publications (e.g., past 5 years)
- Do **not** describe each article separately; instead, group sources by common themes, methods, or viewpoints
- **Avoid repeating** basic background information already provided in the Introduction

### 3. Structure
Organize the review around:
- **Theoretical foundations** relevant to the research questions
- **Methodological approaches** used in the field
- **Key findings and their implications**
- **Debates and controversies** in the literature
- **Research gaps** that lead naturally to your proposed study

### 4. Coherence with Introduction
- Reference the **research questions** established in the Introduction
- Build upon the **research gap** identified earlier
- Use phrases like "建基于前述研究问题" or "针对引言中提出的..."
- Ensure the literature review **logically leads** to the need for your proposed research

### 5. Tone & Style
- Use academic, objective, and analytical language
- Write as a **critical synthesis**, not just a summary
- Demonstrate **analytical thinking** by comparing and contrasting different approaches
- Reference papers using the provided citation system

---

📌 Please return a **Markdown-formatted literature review** of at least 800 words, organized with clear subheadings.

The literature review should complement and deepen the foundation laid in the Introduction, providing a comprehensive academic context for the proposed research.
**Important Note**: This section should focus *only* on the critical review of existing literature. **Do not include** timelines, expected outcomes, or a general summary/outlook for the entire proposal, as these will be covered in a separate "Conclusion" section.
"""

PROJECT_DESIGN_PROMPT = """
You are an academic researcher specializing in research methodology and project design.

The user is preparing a **research proposal** in the field of:
**"{research_field}"**

You have access to the following sections already completed:
- ✅ **Introduction** (includes the research questions and identified research gap)
- ✅ **Literature Review** (provides the theoretical context and previous methodological approaches)

---

🎯 Your task is to **write the Study / Project Design section** of the proposal.  
This section should clearly explain how the user intends to carry out the research in order to answer the research questions outlined in the Introduction, building logically upon the literature analysis.

---

## ✍️ Guidelines for Writing:

### 1. Purpose
The Study / Project Design section should:
- Describe **what data or sources** will be used (e.g., text, experiments, datasets, case studies)
- Explain **how the data will be collected, organized, and managed**
- Identify the **theoretical frameworks and methodological techniques** that will be used for analysis
- Justify **why these methods and sources are suitable** for answering the research questions

### 2. Connection to Prior Sections
- Build directly upon the **research gap and questions** stated in the Introduction
- Reflect on and **incorporate or depart from** the methods used in the Literature Review
- Ensure the design **responds clearly to the research objectives**

### 3. Structure and Detail
Organize your content as follows：

#### a. Data and Sources
- What kinds of data will be used?
- Where will this data come from?
- How will it be accessed and validated?

#### b. Methods and Analysis
- What methodological strategies will be used (qualitative, quantitative, mixed)?
- What analytical tools, software, or theoretical lenses will guide the interpretation?
- How will these methods help explore the key concepts and relationships identified earlier?

#### c. Activities and Workflow
- Provide a **clear and logical sequence** of research activities (e.g., data collection → preprocessing → analysis)
- Briefly note **how each activity contributes** to answering the research question

#### d. Limitations and Challenges
- Anticipate possible **challenges or limitations** in your chosen design (e.g., data access, sample size, ethical concerns)
- Suggest **strategies to mitigate** these limitations

---

### 4. Tone & Style
- Use formal academic language
- Be specific, logical, and practical
- Avoid vague or generic statements (e.g., “I will analyze the data” → explain *how*, *why*, *with what*)

---

📌 Please return a **Markdown-formatted project design section** of at least 800 words.  
Use subheadings where appropriate. Ensure coherence with the Introduction and Literature Review.
**Important Note**: This section should focus *only* on the research design and methodology. **Do not include** timelines, expected outcomes, or a general summary of the entire proposal, as these will be covered in a separate "Conclusion" section.
"""

CONCLUSION_PROMPT = """
You are an academic assistant responsible for writing the **Conclusion section** of a research proposal.

The user has already written the following parts:
- ✅ Introduction (with research background, gap, and research questions)
- ✅ Literature Review (analyzing prior work and framing the context)
- ✅ Project Design (explaining data sources, methods, and research workflow)

Your task is to **write a well-structured conclusion section in Chinese** for the proposal that includes:

---

## ✍️ What to include (All content in Chinese):

### 1. 时间线 (Timeline)
- Present a realistic **timeline for completing the research project**, typically divided by months or phases (e.g., Month 1–3, 4–6…).
- Link each time segment to corresponding activities: literature review, data collection, analysis, writing, editing, etc.
- Reflect awareness of prior work already completed and upcoming milestones.
- Mention any external research-related activities planned (e.g., submitting to conferences or journals).

### 2. 预期成果 (Expected Outcomes)
- List the key **deliverables** or outcomes expected from the research:
  - Academic outputs (e.g., thesis, papers, prototypes, datasets)
  - Contributions to theory or practice
  - Potential publication or application opportunities
- These should relate clearly to the research questions and methods outlined earlier.

### 3. 最终总结 (Final Summary)
- Concisely reaffirm the **importance of the research** and how it builds upon the earlier sections.
- Emphasize feasibility and the contribution to the field.
- Reconnect with the research gap identified in the Introduction and how the plan addresses it.

---

## ✅ Format & Style (All content in Chinese)

- Use **Markdown format** with section headers as specified below (these headers should also be in Chinese if possible, or use the English ones if the LLM handles it better for structure, but the content must be Chinese):
  - `### 时间线`
  - `### 预期成果`
  - `### 最终总结`
- Use **academic, clear, and concise Chinese language**.
- The total content should be around **500–700 words (Chinese characters)**.
- Ensure it logically follows from the previous parts and avoids introducing completely new ideas.

📌 Important: The conclusion should leave the reader confident that the research plan is feasible, coherent, and valuable. **All output for this section must be in Chinese.**
"""


