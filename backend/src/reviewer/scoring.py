"""
ReviewerAgent 的评分标准和评分逻辑
"""

from typing import Dict, List, Any, Tuple
import re

# 定义各维度的评分标准
SCORING_RUBRICS = {
    "结构完整性": {
        "description": "评估研究计划的组织结构是否完整、逻辑是否清晰",
        "criteria": {
            "9-10": "结构完整，各部分比例恰当，逻辑流畅，层次分明",
            "7-8": "结构基本完整，主要部分均有覆盖，逻辑较为清晰",
            "5-6": "结构有基本框架，但某些部分不足或比例不当",
            "3-4": "结构不完整，缺少重要部分，或逻辑混乱",
            "1-2": "结构严重不完整，逻辑混乱，难以理解"
        }
    },
    "学术严谨性": {
        "description": "评估研究内容的学术价值、引用是否恰当、表述是否客观",
        "criteria": {
            "9-10": "学术表述严谨，引用充分且恰当，观点客观中立",
            "7-8": "学术表述较为严谨，引用基本恰当，观点较为客观",
            "5-6": "学术表述一般，引用不足或不够恰当，个别主观表述",
            "3-4": "学术表述不严谨，引用很少或不恰当，多有主观表述",
            "1-2": "缺乏学术严谨性，几乎无引用，表述主观随意"
        }
    },
    "方法适当性": {
        "description": "评估研究方法的选择是否合理、描述是否详细",
        "criteria": {
            "9-10": "方法选择恰当且创新，描述详尽，并充分说明选择理由",
            "7-8": "方法选择合理，描述较为详细，有一定选择理由",
            "5-6": "方法选择基本合理，描述一般，理由不够充分",
            "3-4": "方法选择欠合理，描述简略，缺乏选择理由",
            "1-2": "方法选择不当或缺失，几乎无具体描述"
        }
    },
    "创新价值": {
        "description": "评估研究点是否新颖、有实际或理论价值",
        "criteria": {
            "9-10": "研究角度高度创新，具有重要的理论或实践价值",
            "7-8": "研究有一定创新性，具有较好的理论或实践价值",
            "5-6": "研究有一些新的元素，有一定的学术或应用价值",
            "3-4": "研究创新性不足，价值有限",
            "1-2": "研究几乎无创新点，价值很低"
        }
    },
    "可行性": {
        "description": "评估计划是否切实可行、时间安排是否合理",
        "criteria": {
            "9-10": "计划细致具体，资源需求明确，时间安排合理，高度可行",
            "7-8": "计划较为具体，基本考虑到资源需求，时间安排较为合理",
            "5-6": "计划基本可行，但资源考虑不全面或时间安排不够合理",
            "3-4": "计划可行性较低，资源需求不明确，时间安排不合理",
            "1-2": "计划明显不可行，几乎未考虑实际资源和时间限制"
        }
    },
    "文献整合": {
        "description": "评估文献引用是否充分、整合是否恰当",
        "criteria": {
            "9-10": "文献覆盖全面，整合紧密，与研究设计高度相关",
            "7-8": "文献覆盖较广，整合较好，与研究设计相关",
            "5-6": "文献覆盖一般，整合基本合理，与研究有一定相关性",
            "3-4": "文献覆盖不足，整合不够，与研究相关性低",
            "1-2": "文献极少，几乎无整合，与研究关联性很弱"
        }
    }
}

def determine_research_field_category(research_field: str) -> str:
    """根据研究领域确定评分类别"""
    
    # 领域关键词映射表
    field_keywords = {
        "computer_science": [
            "计算机", "人工智能", "机器学习", "深度学习", "自然语言处理", "计算机视觉", 
            "数据库", "软件工程", "算法", "网络安全", "区块链", "大数据", "云计算",
            "computer", "ai", "artificial intelligence", "machine learning", "deep learning", 
            "nlp", "algorithm", "programming", "software", "database", "network"
        ],
        "medicine": [
            "医学", "医疗", "临床", "疾病", "诊断", "治疗", "药物", "护理", "健康", 
            "医院", "患者", "医生", "药理", "外科", "内科", "病理", "免疫",
            "medicine", "medical", "clinical", "disease", "diagnosis", "treatment", 
            "pharmaceutical", "healthcare", "hospital", "patient", "doctor"
        ],
        "social_science": [
            "社会", "心理学", "社会学", "经济", "政治", "文化", "教育", "管理", 
            "人类学", "考古", "历史", "地理", "民族", "传播", "语言学", "法律",
            "social", "psychology", "sociology", "economy", "politics", "culture", 
            "education", "management", "anthropology", "archaeology", "history", "geography"
        ],
        "engineering": [
            "工程", "机械", "电气", "土木", "化工", "材料", "结构", "建筑", "能源", 
            "制造", "自动化", "控制", "测量", "航空", "航天", "汽车", "电子",
            "engineering", "mechanical", "electrical", "civil", "chemical", "material", 
            "structure", "construction", "energy", "manufacturing", "automation", "control"
        ],
        "education": [
            "教育", "学习", "教学", "课程", "学校", "师资", "学生", "培训", "教材", 
            "教育技术", "教育心理", "教育管理", "课堂", "学业", "考试", "教师",
            "education", "learning", "teaching", "curriculum", "school", "student", 
            "training", "classroom", "academic", "assessment", "teacher"
        ]
    }
    
    # 将研究领域转为小写以便匹配
    lowered_field = research_field.lower()
    
    # 尝试匹配研究领域与关键词
    for category, keywords in field_keywords.items():
        for keyword in keywords:
            if keyword.lower() in lowered_field:
                return category
    
    # 如果没有匹配到任何类别，返回默认类别
    return "default"

def extract_section_content(full_content: str, section_name: str) -> str:
    """从完整内容中提取特定章节的内容"""
    
    # 常见章节标题模式
    section_patterns = {
        "引言": [r"#\s*引言", r"#\s*1[\.\s]+\s*引言", r"#\s*绪论", r"#\s*Introduction", r"#\s*1[\.\s]+\s*Introduction"],
        "文献综述": [r"#\s*文献综述", r"#\s*2[\.\s]+\s*文献综述", r"#\s*Literature Review", r"#\s*2[\.\s]+\s*Literature Review"],
        "研究设计": [r"#\s*研究设计", r"#\s*3[\.\s]+\s*研究设计", r"#\s*研究方法", r"#\s*Research Design", r"#\s*Research Method"],
        "结论": [r"#\s*结论", r"#\s*4[\.\s]+\s*结论", r"#\s*Conclusion", r"#\s*总结与展望"]
    }
    
    # 尝试查找章节开始位置
    start_pos = -1
    end_pos = len(full_content)
    
    # 如果没有预定义的模式，尝试直接查找章节名
    if section_name not in section_patterns:
        section_patterns[section_name] = [rf"#\s*{section_name}"]
    
    # 尝试使用预定义模式查找章节起始位置
    for pattern in section_patterns[section_name]:
        match = re.search(pattern, full_content, re.IGNORECASE)
        if match:
            start_pos = match.start()
            break
    
    # 如果没找到，返回空字符串
    if start_pos == -1:
        return ""
    
    # 查找下一个章节，确定当前章节结束位置
    next_section_pattern = r"#\s*[1-9]?[\.\s]*[^#]+"
    next_matches = list(re.finditer(next_section_pattern, full_content[start_pos+1:]))
    if next_matches:
        # 第一个匹配的就是下一节的开始
        end_pos = start_pos + 1 + next_matches[0].start()
    
    # 提取并返回章节内容
    return full_content[start_pos:end_pos].strip()

def analyze_section_proportions(full_content: str) -> Dict[str, float]:
    """分析各个章节的内容比例"""
    sections = ["引言", "文献综述", "研究设计", "结论"]
    section_contents = {}
    section_proportions = {}
    
    # 提取各章节内容
    for section in sections:
        content = extract_section_content(full_content, section)
        section_contents[section] = content
    
    # 计算总内容长度
    total_length = sum(len(content) for content in section_contents.values())
    
    # 计算各章节比例
    if total_length > 0:
        section_proportions = {
            section: round(len(content) / total_length * 100, 2) 
            for section, content in section_contents.items()
        }
    
    return section_proportions

def count_citations(full_content: str) -> int:
    """计算引用次数"""
    citation_pattern = r"\[\d+(,\s*\d+)*\]"  # 匹配形如 [1], [1,2], [1, 2, 3] 的引用
    citations = re.findall(citation_pattern, full_content)
    return len(citations)

def extract_reference_count(full_content: str) -> int:
    """提取参考文献数量"""
    # 尝试找到参考文献部分
    ref_section = extract_section_content(full_content, "参考文献")
    if not ref_section:
        # 如果找不到独立的参考文献部分，尝试在全文中寻找
        ref_pattern = r"参考文献\s*\n([\s\S]*?)(?=\n#|\Z)"
        match = re.search(ref_pattern, full_content)
        if match:
            ref_section = match.group(1)
    
    # 如果找到参考文献部分，计算条目数量
    if ref_section:
        # 匹配类似 [1] Author... 的参考文献条目
        ref_entries = re.findall(r"\[\d+\]", ref_section)
        return len(ref_entries)
    
    return 0

def calculate_metadata_scores(proposal_content: str) -> Dict[str, Any]:
    """基于元数据计算一些初步评分指标"""
    metadata_scores = {}
    
    # 分析章节比例
    section_proportions = analyze_section_proportions(proposal_content)
    metadata_scores["section_proportions"] = section_proportions
    
    # 理想的章节比例(%)：引言15-20%，文献综述25-35%，研究设计30-40%，结论10-15%
    ideal_proportions = {
        "引言": (15, 20),
        "文献综述": (25, 35),
        "研究设计": (30, 40),
        "结论": (10, 15)
    }
    
    # 计算章节比例得分
    proportion_scores = {}
    for section, (min_prop, max_prop) in ideal_proportions.items():
        if section in section_proportions:
            actual_prop = section_proportions[section]
            if min_prop <= actual_prop <= max_prop:
                # 在理想范围内，得满分10分
                proportion_scores[section] = 10
            elif actual_prop < min_prop:
                # 低于理想最小值，按比例计分
                proportion_scores[section] = round(10 * actual_prop / min_prop, 1)
            else:
                # 高于理想最大值，超出部分扣分
                excess_ratio = (actual_prop - max_prop) / max_prop
                proportion_scores[section] = max(5, round(10 - 5 * excess_ratio, 1))
        else:
            # 章节缺失，得0分
            proportion_scores[section] = 0
    
    metadata_scores["proportion_scores"] = proportion_scores
    
    # 计算平均章节比例得分
    if proportion_scores:
        metadata_scores["avg_proportion_score"] = round(
            sum(proportion_scores.values()) / len(proportion_scores), 1
        )
    else:
        metadata_scores["avg_proportion_score"] = 0
    
    # 计算引用次数
    citation_count = count_citations(proposal_content)
    metadata_scores["citation_count"] = citation_count
    
    # 提取参考文献数量
    reference_count = extract_reference_count(proposal_content)
    metadata_scores["reference_count"] = reference_count
    
    # 计算引用/参考文献比率（引用密度）
    if reference_count > 0:
        citation_density = citation_count / reference_count
        metadata_scores["citation_density"] = round(citation_density, 2)
    else:
        metadata_scores["citation_density"] = 0
    
    # 合理的引用密度应该在1.5-4之间，过低或过高都不理想
    if 1.5 <= metadata_scores.get("citation_density", 0) <= 4:
        metadata_scores["citation_score"] = 10
    elif metadata_scores.get("citation_density", 0) < 1.5:
        density = metadata_scores.get("citation_density", 0)
        metadata_scores["citation_score"] = round(10 * density / 1.5, 1)
    else:  # > 4
        excess = metadata_scores.get("citation_density", 0) - 4
        metadata_scores["citation_score"] = max(5, round(10 - excess, 1))
    
    return metadata_scores