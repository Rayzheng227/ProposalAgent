"""
ReviewerAgent 使用的提示模板
"""

GENERAL_REVIEW_PROMPT = """
你是一位专业的研究计划评审专家，需要对以下研究计划书进行全面评审。评审应基于学术标准和研究方法论，关注内容质量、结构完整性和学术严谨性。

研究主题：{research_field}

## 评审内容
{content_to_review}

## 评审要求
请根据以下几个维度进行评分（1-10分）和具体点评：

1. **结构完整性**：评估研究计划的组织结构是否完整、逻辑是否清晰
2. **学术严谨性**：评估研究内容的学术价值、引用是否恰当、表述是否客观
3. **方法适当性**：评估研究方法的选择是否合理、描述是否详细
4. **创新价值**：评估研究点是否新颖、有实际或理论价值
5. **可行性**：评估计划是否切实可行、时间安排是否合理
6. **文献整合**：评估文献引用是否充分、整合是否恰当
7. **{field_specific_criterion}**：{field_specific_description}

## 输出格式要求
请提供JSON格式的评审结果，包含以下字段：
```json
{{
  "scores": {{
    "结构完整性": 分数,
    "学术严谨性": 分数,
    "方法适当性": 分数,
    "创新价值": 分数,
    "可行性": 分数,
    "文献整合": 分数,
    "{field_specific_criterion}": 分数,
    "总体评分": 平均分数
  }},
  "strengths": [
    "优势点1",
    "优势点2",
    ...
  ],
  "weaknesses": [
    "不足点1",
    "不足点2",
    ...
  ],
  "improvement_suggestions": [
    {{
      "section": "具体章节",
      "issue": "问题描述",
      "suggestion": "改进建议",
      "priority": "高/中/低"
    }},
    ...
  ],
  "overall_comments": "总体评审意见"
}}
```
"""

SECTION_REVIEW_PROMPT = """
你是一位专业的研究计划评审专家，需要对以下研究计划书的特定部分进行深入评审。

研究主题：{research_field}

## 评审部分：{section_name}
{section_content}

## 评审要求
请对此{section_name}部分进行详细评审，关注以下方面：
1. 内容完整性：是否包含该部分应有的所有要素
2. 逻辑连贯性：论述是否清晰，逻辑是否自洽
3. 学术规范：表述是否专业，引用是否恰当
4. 与整体研究目标的一致性：是否符合研究领域和问题的要求
5. 特定标准：{section_specific_requirements}

## 输出格式要求
请提供JSON格式的评审结果，包含以下字段：
```json
{{
  "section_score": 分数(1-10),
  "strengths": [
    "优势点1",
    "优势点2",
    ...
  ],
  "weaknesses": [
    "不足点1",
    "不足点2",
    ...
  ],
  "specific_suggestions": [
    {{
      "issue": "问题描述",
      "location": "具体位置",
      "suggestion": "具体修改建议",
      "reason": "建议理由"
    }},
    ...
  ],
  "section_comments": "部分评审总结"
}}
```
"""

REVISION_GUIDANCE_PROMPT = """
作为研究计划书修订顾问，你的任务是将评审反馈转化为明确的修订指南。基于以下评审反馈，生成可直接指导ProposalAgent改进的具体指令。

## 研究主题
{research_field}

## 评审反馈
{review_feedback}

## 特定关注点
{specific_focus}

## 输出要求
请生成结构化的修订指南，包含以下内容：
```json
{{
  "revision_focus": "修订重点简述",
  "revision_instructions": [
    {{
      "target_section": "目标章节",
      "operation": "添加/修改/删除/重组",
      "specific_instruction": "详细的修改指南",
      "reasoning": "修改理由",
      "examples": "示例或参考"
    }},
    ...
  ],
  "content_enhancement_suggestions": {{
    "引言": ["具体建议1", "具体建议2", ...],
    "文献综述": ["具体建议1", "具体建议2", ...],
    "研究设计": ["具体建议1", "具体建议2", ...],
    "结论": ["具体建议1", "具体建议2", ...]
  }},
  "priority_order": ["首要修改项", "次要修改项", ...]
}}
```

确保你的修订指南是具体的、可操作的，并与原始研究计划的内容和结构紧密相关。
"""

# 添加领域特定评审标准
FIELD_SPECIFIC_RUBRICS = {
    "computer_science": {
        "criterion": "技术创新性",
        "description": "评估研究在计算机科学领域的技术创新程度和潜在影响"
    },
    "medicine": {
        "criterion": "临床价值",
        "description": "评估研究对临床实践的潜在贡献和医疗实用性"
    },
    "social_science": {
        "criterion": "社会影响",
        "description": "评估研究对社会问题理解和解决的潜在贡献"
    },
    "engineering": {
        "criterion": "工程实用性",
        "description": "评估研究成果在工程领域的应用潜力和实际价值"
    },
    "education": {
        "criterion": "教学应用性",
        "description": "评估研究对教育实践和学习方法的潜在改进"
    },
    "default": {
        "criterion": "领域价值",
        "description": "评估研究在该特定领域的学术价值和实际应用前景"
    }
}