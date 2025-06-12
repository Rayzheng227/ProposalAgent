import os
import re
import glob
import subprocess
from datetime import datetime
from typing import Dict, List
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
Api_key = os.getenv('DASHSCOPE_API_KEY')
base_url = os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')

class ProposalExporter:
    def __init__(self, api_key: str = None, base_url: str = None):
        """
        初始化导出器
        :param api_key: 千问API密钥
        :param base_url: API基础URL
        """
        # 使用千问大模型配置，与graph.py保持一致
        self.llm = ChatOpenAI(
            api_key=Api_key,
            model="qwen-turbo-latest", 
            base_url=base_url or os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
            temperature=0,
            # max_tokens=4000  # 限制输出长度，避免超出模型限制
        )
        
        self.template_path = "exporter/main.tex"
        self.markdown_source_dir = "output"  # Markdown文件的源目录
        self.output_dir = "exporter/pdf_output"       # TeX/PDF的输出目录
        self.exporter_dir = "exporter"       # exporter目录路径 (包含cls, main.tex, figures)
        
    def read_template(self) -> str:
        """读取LaTeX模板文件"""
        with open(self.template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def read_markdown_files(self, specific_file: str = None) -> Dict[str, str]:
        """
        读取Markdown文件
        :param specific_file: 指定文件名，如果为None则自动选择最新文件
        """
        md_files = {}
        
        if specific_file:
            # 读取指定文件
            file_path = os.path.join(self.markdown_source_dir, specific_file) # 使用 markdown_source_dir
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    md_files[specific_file] = content
                print(f"✓ 读取指定文件: {file_path}")
            else:
                print(f"⚠️ 指定文件不存在: {file_path}")
        else:
            # 自动选择最新文件
            pattern = os.path.join(self.markdown_source_dir, "*.md") # 使用 markdown_source_dir
            all_md_files = glob.glob(pattern)
            
            if all_md_files:
                # 按修改时间排序，选择最新的文件
                latest_file = max(all_md_files, key=os.path.getmtime)
                filename = os.path.basename(latest_file)
                
                with open(latest_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    md_files[filename] = content
                
                print(f"✓ 自动选择最新文件: {latest_file}")
                print(f"  文件修改时间: {datetime.fromtimestamp(os.path.getmtime(latest_file))}")
            else:
                print(f"⚠️ 在目录 '{self.markdown_source_dir}' 中未找到任何Markdown文件")
        
        return md_files
    
    def truncate_content(self, content: str, max_length: int = 120000) -> str:
        """
        截断内容以避免超出模型输入限制
        """
        if len(content) > max_length:
            truncated = content[:max_length]
            # 尝试在完整句子处截断
            last_period = truncated.rfind('。')
            last_newline = truncated.rfind('\n')
            cut_point = max(last_period, last_newline)
            
            if cut_point > max_length * 0.8:  # 如果找到的截断点不会丢失太多内容
                return truncated[:cut_point + 1]
            else:
                return truncated
        return content
    
    def clean_duplicate_numbering(self, latex_content: str) -> str:
        """清理重复的章节编号、中文编号以及残留的Markdown标题标记。"""
        lines = latex_content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            original_line_for_logging = line.strip() # For logging/commenting if removed/changed
            
            # Rule 1: Clean LaTeX section commands for duplicate numbering
            if '\\section{' in line:
                line = re.sub(r'\\section\{[\d\.]+\s*', r'\\section{', line)
                line = re.sub(r'\\section\{[（(][一二三四五六七八九十]+[）)]\s*', r'\\section{', line)
            elif '\\subsection{' in line:
                line = re.sub(r'\\subsection\{[\d\.]+\s*', r'\\subsection{', line)
                line = re.sub(r'\\subsection\{[（(][一二三四五六七八九十]+[）)]\s*', r'\\subsection{', line)
            elif '\\subsubsection{' in line:
                line = re.sub(r'\\subsubsection\{[\d\.]+\s*', r'\\subsubsection{', line)
                line = re.sub(r'\\subsubsection\{[（(][一二三四五六七八九十]+[）)]\s*', r'\\subsubsection{', line)
            
            # Rule 2: Handle stray Markdown-like headings
            stripped_line = line.strip()
            if stripped_line.startswith('#') and not stripped_line.startswith('%'):
                md_heading_match = re.match(r'^\s*(#+)\s*(.*)', stripped_line)
                if md_heading_match:
                    hashes = md_heading_match.group(1)
                    title_text_raw = md_heading_match.group(2).strip()
                    
                    # Clean title_text_raw from further Markdown list/heading markers
                    title_text_cleaned = re.sub(r'^\s*([#\*\-]\s*)+', '', title_text_raw).strip()

                    if not title_text_cleaned: # If only hashes or markers, comment out
                        cleaned_lines.append(f"% Removed empty MD remnant: {original_line_for_logging}")
                        continue

                    # Convert to appropriate LaTeX sectioning command
                    num_hashes = len(hashes)
                    # If title_text_raw itself contained hashes, count them too for level
                    # e.g. "# ### title" -> hashes="#", title_text_raw="### title"
                    # We need to determine the true intended level.
                    # Let's count effective hashes:
                    effective_hashes = num_hashes
                    if title_text_raw.startswith('#'):
                        inner_hashes_match = re.match(r'^\s*(#+)', title_text_raw)
                        if inner_hashes_match:
                            effective_hashes += len(inner_hashes_match.group(1))
                            title_text_cleaned = re.sub(r'^\s*#+\s*', '', title_text_raw).strip()
                    
                    if effective_hashes == 1: # Typically \chapter, but we use \section for top-level from MD
                        cleaned_lines.append(f"\\section{{{title_text_cleaned}}} % Converted MD remnant: {original_line_for_logging}")
                    elif effective_hashes == 2:
                        cleaned_lines.append(f"\\section{{{title_text_cleaned}}} % Converted MD remnant: {original_line_for_logging}")
                    elif effective_hashes == 3:
                        cleaned_lines.append(f"\\subsection{{{title_text_cleaned}}} % Converted MD remnant: {original_line_for_logging}")
                    elif effective_hashes >= 4:
                        cleaned_lines.append(f"\\subsubsection{{{title_text_cleaned}}} % Converted MD remnant: {original_line_for_logging}")
                    else: # Should not happen if md_heading_match was successful
                        cleaned_lines.append(f"% Problematic MD remnant (unhandled hash count): {original_line_for_logging}")
                    continue # Move to next line after handling
                else:
                    # Line starts with # but not a clear MD heading (e.g., #no_space_title)
                    # This is likely an error or needs specific handling if it's a valid LaTeX construct (rare for #)
                    cleaned_lines.append(f"% Problematic line (starts with #, not MD heading): {original_line_for_logging}")
                    continue # Move to next line

            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def clean_markdown_numbering(self, content: str) -> str:
        """清理Markdown内容中的重复编号和中文编号"""
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 清理标题中的数字编号和中文编号
            if line.strip().startswith('#'):
                # 移除## 3.2 这样的编号
                line = re.sub(r'^(#+)\s*[\d\.]+\s*', r'\1 ', line)
                # 移除## （二）这样的中文编号
                line = re.sub(r'^(#+)\s*[（(][一二三四五六七八九十]+[）)]\s*', r'\1 ', line)
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def simple_md_to_latex(self, markdown_content: str) -> str:
        """简单的Markdown到LaTeX转换（备用方案）"""
        content = markdown_content
        
        # 转换标题，同时清理编号和中文编号
        content = re.sub(r'^#### [\d\.]*\s*[（(]*[一二三四五六七八九十]*[）)]*\s*(.*?)$', r'\\subsubsection{\1}', content, flags=re.MULTILINE)
        content = re.sub(r'^### [\d\.]*\s*[（(]*[一二三四五六七八九十]*[）)]*\s*(.*?)$', r'\\subsection{\1}', content, flags=re.MULTILINE)
        content = re.sub(r'^## [\d\.]*\s*[（(]*[一二三四五六七八九十]*[）)]*\s*(.*?)$', r'\\section{\1}', content, flags=re.MULTILINE)
        
        # 转换加粗和斜体
        content = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', content)
        content = re.sub(r'\*(.*?)\*', r'\\textit{\1}', content)
        
        # 移除其他Markdown标记
        content = re.sub(r'^# .*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*[-*+]\s+', '', content, flags=re.MULTILINE)
        
        return content.strip()
    
    def extract_title(self, content: str) -> str:
        """提取标题"""
        # 首先尝试从第一行或明显的标题标记中提取
        lines = content.split('\n')
        for line in lines[:10]:  # 检查前10行
            if line.strip().startswith('#'):
                title = re.sub(r'^#+\s*', '', line.strip())
                # 清理标题，移除特殊字符和编号
                title = re.sub(r'：.*$', '', title)  # 移除冒号后的内容
                title = re.sub(r'研究计划书[：:]?\s*', '', title)  # 秼除"研究计划书："
                # 如果清理后的标题太短或为空，尝试提取冒号后的内容
                if len(title.strip()) < 3:
                    # 重新提取，这次保留冒号后的内容
                    original_line = re.sub(r'^#+\s*', '', line.strip())
                    if '：' in original_line:
                        title = original_line.split('：', 1)[1].strip()
                    elif ':' in original_line:
                        title = original_line.split(':', 1)[1].strip()
                    else:
                        title = original_line
                
                if title.strip():
                    return title.strip()
        
        # 如果从标题行没有提取到有效标题，尝试从文件名提取
        # 查找文件名中可能包含的研究主题
        for filename in content.split('\n')[:5]:  # 检查前5行是否有文件名信息
            if 'Research_Proposal_' in filename and '.md' in filename:
                # 从文件名中提取主题
                match = re.search(r'Research_Proposal_([^_]+)', filename)
                if match:
                    topic = match.group(1)
                    # 清理可能的编码问题
                    topic = topic.replace('_', ' ').strip()
                    if len(topic) > 3:
                        return topic
        
        # 使用大模型提取标题
        truncated_content = self.truncate_content(content, 1000)
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            prompt = f"""
从以下文本中提取一个合适的研究计划标题，要求简洁明确，适合学术论文：

{truncated_content}

请只返回标题文字，不要包含任何标点符号或格式标记，不要包含"研究计划书"等词汇，最多20个字：
"""
            
            response = self.llm.invoke([
                SystemMessage(content="你是一个标题提取助手，专门为学术研究计划生成合适的标题。"),
                HumanMessage(content=prompt)
            ])
            extracted_title = response.content.strip()
            # 清理可能的前缀
            extracted_title = re.sub(r'^研究计划书[：:]\s*', '', extracted_title)
            return extracted_title
        except Exception as e:
            print(f"提取标题失败: {e}")
            return "人工智能在医疗领域的应用研究"

    def convert_md_to_latex(self, markdown_content: str, section_type: str) -> str:
        """
        使用大模型将Markdown内容转换为LaTeX格式
        """
        # 截断内容以避免超出模型限制
        truncated_content = self.truncate_content(markdown_content, 60000)
        
        prompt = f"""
请将以下Markdown内容转换为LaTeX格式，用于学术论文的{section_type}部分：

要求：
1. 将## 标题转换为 \\section{{}}
2. 将### 标题转换为 \\subsection{{}}
3. 将#### 标题转换为 \\subsubsection{{}}
4. 保持段落格式，确保中文排版正确
5. 将引用格式[数字]保持为[数字]格式
6. 将加粗文本转换为\\textbf{{}}
7. 将斜体文本转换为\\textit{{}}
8. 删除Markdown语法标记，只保留纯文本和LaTeX命令
9. 最多返回2000字的内容
10. **重要：直接返回LaTeX内容，不要使用```latex```或其他代码块标记包裹**
11. **重要：避免重复的章节编号，如果内容中已有编号，请移除或调整**
12. **重要：移除所有中文编号如（一）、（二）、（三）等，只保留纯标题文字**

Markdown内容：
{truncated_content}

请只返回转换后的纯LaTeX内容，不要包含任何代码块标记，不要包含中文编号：
"""
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            response = self.llm.invoke([
                SystemMessage(content="你是一个专业的LaTeX格式转换助手。请直接返回LaTeX代码，不要使用任何markdown代码块标记包裹，同时移除所有中文编号。"),
                HumanMessage(content=prompt)
            ])
            
            latex_content = response.content.strip()
            
            # 更健壮地移除代码块标记，处理LLM可能在代码块前后添加额外文本的情况
            extracted_payload = latex_content # 默认使用全部内容

            # 尝试从 ```latex ... ``` 中提取
            match_latex = re.search(r'```latex\s*(.*?)\s*```', latex_content, re.DOTALL | re.IGNORECASE)
            if match_latex:
                extracted_payload = match_latex.group(1).strip()
            else:
                # 如果没有 ```latex，尝试从 ``` ... ``` 中提取
                match_generic = re.search(r'```\s*(.*?)\s*```', latex_content, re.DOTALL)
                if match_generic:
                    extracted_payload = match_generic.group(1).strip()
            # 如果没有找到任何代码块标记, extracted_payload 保持为原始的 latex_content

            # 清理提取出（或原始）的 payload
            # clean_duplicate_numbering 会处理数字编号、中文编号以及残留的Markdown标题
            cleaned_payload = self.clean_duplicate_numbering(extracted_payload)
            
            return cleaned_payload.strip()
        except Exception as e:
            print(f"转换失败: {e}")
            # Fallback也应该清理
            simple_latex = self.simple_md_to_latex(markdown_content)
            return self.clean_duplicate_numbering(simple_latex).strip()

    def extract_section_content(self, content: str, section_name: str) -> str:
        """提取特定章节的内容"""
        # 截断内容以避免超出模型限制
        truncated_content = self.truncate_content(content, 80000)
        
        prompt_text = f"""
从以下文本中提取与"{section_name}"相关的内容。请只返回相关的段落内容，保持原有的Markdown格式。

如果文本中有明确的章节标题，请优先提取对应章节的内容。如果没有明确的章节标题，请根据内容含义提取相关段落。
"""
        if section_name == "总结":
            prompt_text += """
特别注意：当提取"总结"部分时，请确保内容主要对应研究的最终结论、成果总结、未来展望，或者明确标记为"第四部分"、"结论与展望"等末尾章节。
如果"总结"内容紧跟在"研究内容"或"第三部分"之后，请准确识别"总结"部分的起始点，避免包含前面章节的详细主体内容。
"""
        elif section_name == "研究内容":
            prompt_text += """
特别注意：当提取"研究内容"部分时，请确保内容主要对应研究方法、研究设计、数据来源、分析工具等具体的研究实施方案。
请重点查找标题为"研究设计"、"研究方法"、"数据和来源"、"方法和分析"、"活动和工作流程"等章节的内容。
不要包含引言、文献综述等前文内容，只提取与具体研究实施相关的部分。
"""
        
        prompt_text += f"""
要求：
1. 保持原有的Markdown格式
2. 包含完整的段落，不要截断句子
3. 如果有多个相关段落，都要包含
4. 最多返回1000字的内容
5. **避免重复的章节编号，如果原文中有数字编号，请在提取时清理**

文本内容：
{truncated_content}
"""
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            response = self.llm.invoke([
                SystemMessage(content=f"你是一个内容提取助手，专门从学术文本中提取{section_name}相关的内容。请保持内容的完整性和准确性，同时避免重复编号。"),
                HumanMessage(content=prompt_text)
            ])
            
            # 清理可能的重复编号
            extracted_content = response.content.strip()
            extracted_content = self.clean_markdown_numbering(extracted_content)
            
            return extracted_content
        except Exception as e:
            print(f"提取{section_name}内容失败: {e}")
            # 使用简单的文本匹配作为备用方案
            return self.simple_section_extraction(content, section_name)

    def simple_section_extraction(self, content: str, section_name: str) -> str:
        """简单的章节内容提取（备用方案）"""
        lines = content.split('\n')
        
        # 定义章节关键词映射
        section_keywords = {
            '引言': ['引言', '介绍', '背景', '研究背景', '问题提出', '研究主题', '第一部分'],
            '文献综述': ['文献综述', '相关工作', '研究现状', '理论基础', '文献回顾', '第二部分'],
            '研究内容': ['研究设计', '研究方法', '方法论', '技术路线', '实验设计', '数据和来源', '方法和分析', '活动和工作流程', '第三部分'],
            '总结': ['总结', '结论', '展望', '预期成果', '时间安排', '结论与展望', '第四部分', '第4部分']
        }
        
        keywords = section_keywords.get(section_name, [section_name])
        
        # 查找匹配的章节
        section_lines = []
        in_section = False
        found_start = False
        
        for i, line in enumerate(lines):
            # 对于"研究内容"，特别处理以确保找到正确的起始点
            if section_name == "研究内容":
                # 查找"# 研究设计"标题行
                if line.strip().startswith('#') and '研究设计' in line:
                    in_section = True
                    found_start = True
                    section_lines.append(line)
                    continue
                # 如果已经开始，检查是否到了下一个主要章节
                elif in_section and line.strip().startswith('#') and not any(keyword in line for keyword in keywords):
                    # 如果遇到不相关的主要章节标题，结束提取
                    if '参考文献' in line or '附录' in line or len(line.strip()) < 10:
                        break
                    # 检查是否是文档末尾的章节
                    break
                elif in_section:
                    section_lines.append(line)
            else:
                # 原有逻辑保持不变
                if any(keyword in line for keyword in keywords) and ('##' in line or '#' in line):
                    in_section = True
                    section_lines.append(line)
                    continue
                
                # 检查是否到了下一个章节
                if in_section and line.strip().startswith('#') and not any(keyword in line for keyword in keywords):
                    break
                
                if in_section:
                    section_lines.append(line)
        
        result = '\n'.join(section_lines).strip()
        
        # 如果没有找到特定章节，尝试智能匹配内容
        if not result and content:
            # 根据关键词搜索相关段落
            content_lines = content.split('\n')
            relevant_paragraphs = []
            
            for i, line in enumerate(content_lines):
                if any(keyword in line.lower() for keyword in [kw.lower() for kw in keywords]):
                    # 找到关键词，收集该段落及其前后几行
                    start = max(0, i-2)
                    end = min(len(content_lines), i+10)
                    paragraph = '\n'.join(content_lines[start:end])
                    relevant_paragraphs.append(paragraph)
            
            if relevant_paragraphs:
                result = '\n\n'.join(relevant_paragraphs[:2])  # 最多取前两个段落
            else:
                # 最后的备用方案：返回部分内容
                result = content[:1000] + "..." if len(content) > 1000 else content
        
        return result

    def extract_content_by_type(self, md_files: Dict[str, str]) -> Dict[str, str]:
        """
        根据文件名或内容推断并提取对应的章节内容
        """
        content_map = {
            'title': '',
            '引言': '',
            '文献综述': '',
            '研究内容': '',
            '总结': '',
            'time': datetime.now().strftime('%Y年%m月')
        }
        
        # 合并所有Markdown内容
        all_content = '\n\n'.join(md_files.values())
        print(f"总内容长度: {len(all_content)} 字符")
        
        # 提取标题
        title_content = self.extract_title(all_content)
        if title_content:
            content_map['title'] = title_content
            print(f"✓ 提取标题: {title_content}")
        
        # 使用大模型分析和提取内容
        for section in ['引言', '文献综述', '研究内容', '总结']:
            print(f"正在提取 {section} 内容...")
            section_content = self.extract_section_content(all_content, section)
            if section_content:
                print(f"✓ 提取到 {section} 内容，长度: {len(section_content)} 字符")
                print(f"正在转换 {section} 为LaTeX格式...")
                latex_content = self.convert_md_to_latex(section_content, section)
                content_map[section] = latex_content
                print(f"✓ {section} 转换完成")
            else:
                print(f"⚠️ 未找到 {section} 相关内容")
            
        return content_map
    
    def fill_template(self, template: str, content_map: Dict[str, str]) -> str:
        """将提取的内容填入模板"""
        filled_template = template
        
        # 替换占位符
        filled_template = filled_template.replace('[title]', content_map.get('title', '研究计划'))
        filled_template = filled_template.replace('[time]', content_map.get('time', ''))
        filled_template = filled_template.replace('[引言]', content_map.get('引言', ''))
        filled_template = filled_template.replace('[文献综述]', content_map.get('文献综述', ''))
        filled_template = filled_template.replace('[研究内容]', content_map.get('研究内容', ''))
        filled_template = filled_template.replace('[总结]', content_map.get('总结', ''))
        
        return filled_template
    
    def compile_with_xelatex(self, tex_filename: str, output_dir: str = None) -> bool:
        """
        使用xelatex编译LaTeX文件生成PDF
        :param tex_filename: LaTeX文件名 (仅文件名部分，如 'proposal.tex')
        :param output_dir: 输出目录 (如 'exporter/pdf_output')
        :return: 编译是否成功
        """
        if output_dir is None:
            output_dir = self.output_dir

        os.makedirs(output_dir, exist_ok=True)

        tex_basename = os.path.basename(tex_filename) # 确保只取文件名
        tex_name_without_ext = os.path.splitext(tex_basename)[0]
        # tex_full_path 是指在 output_dir 中的路径
        tex_full_path = os.path.join(output_dir, tex_basename)


        print(f"正在使用xelatex编译: {tex_full_path}")

        # 复制 .cls 文件
        cls_source_file = os.path.join(self.exporter_dir, "phdproposal.cls")
        if not os.path.exists(cls_source_file):
            print(f"❌ 找不到类文件: {cls_source_file}")
            return False
        
        import shutil
        target_cls_file = os.path.join(output_dir, "phdproposal.cls")
        try:
            shutil.copy2(cls_source_file, target_cls_file)
            print(f"✓ 已复制类文件到: {target_cls_file}")
        except Exception as e:
            print(f"❌ 复制类文件失败: {e}")
            return False

        # 复制 Logo 文件和 figures 目录
        logo_source_file = os.path.join(self.exporter_dir, "figures", "Logo.png")
        target_figures_dir = os.path.join(output_dir, "figures")
        target_logo_file = os.path.join(target_figures_dir, "Logo.png")

        if os.path.exists(logo_source_file):
            os.makedirs(target_figures_dir, exist_ok=True)
            try:
                shutil.copy2(logo_source_file, target_logo_file)
                print(f"✓ 已复制Logo文件到: {target_logo_file}")
            except Exception as e:
                print(f"❌ 复制Logo文件失败: {e}")
                # 根据需求决定是否在此处返回False，如果Logo是可选的，可以继续
        else:
            print(f"⚠️ 未找到Logo文件: {logo_source_file}，将不包含Logo。")


        try:
            original_cwd = os.getcwd()
            os.chdir(output_dir) # 切换到编译目录
            print(f"当前工作目录: {os.getcwd()}")
            print(f"编译文件: {tex_basename}") # 应该只编译文件名

            result1 = subprocess.run([
                'xelatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                tex_basename
            ], capture_output=True, text=True, timeout=120)

            if result1.returncode != 0:
                print(f"❌ 第一次xelatex编译失败:")
                print(f"标准输出: {result1.stdout}")
                print(f"错误输出: {result1.stderr}")
                log_file = f"{tex_name_without_ext}.log"
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()
                        print(f"Log文件内容:\n{log_content[-1000:]}")
                return False

            print("正在进行第二次编译（处理交叉引用）...")
            result2 = subprocess.run([
                'xelatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                tex_basename
            ], capture_output=True, text=True, timeout=120)

            if result2.returncode != 0:
                print(f"❌ 第二次xelatex编译失败:")
                print(f"错误输出: {result2.stderr}")
                return False

            pdf_filename = f"{tex_name_without_ext}.pdf"
            if os.path.exists(pdf_filename):
                print(f"✅ PDF文件生成成功: {os.path.join(os.getcwd(), pdf_filename)}") # 使用os.getcwd()获取绝对路径
                self._cleanup_temp_files(tex_name_without_ext)
                try:
                    os.remove("phdproposal.cls") # 清理复制的cls文件
                    if os.path.exists(target_figures_dir): # 清理复制的figures目录
                        shutil.rmtree(target_figures_dir)
                    print("✓ 已清理临时类文件和Logo文件")
                except Exception as e:
                    print(f"⚠️ 清理临时文件时出错: {e}")
                    pass
                return True
            else:
                print(f"❌ PDF文件未生成: {pdf_filename}")
                return False

        except subprocess.TimeoutExpired:
            print("❌ xelatex编译超时")
            return False
        except FileNotFoundError:
            print("❌ 未找到xelatex命令，请确保已安装LaTeX环境")
            print("Ubuntu/Debian: sudo apt-get install texlive-full")
            print("CentOS/RHEL: sudo yum install texlive-scheme-full")
            return False
        except Exception as e:
            print(f"❌ 编译过程中发生错误: {e}")
            return False
        finally:
            os.chdir(original_cwd)
    
    def _cleanup_temp_files(self, tex_name_without_ext: str):
        """清理LaTeX编译产生的临时文件"""
        temp_extensions = ['.aux', '.log', '.out', '.toc', '.fdb_latexmk', '.fls', '.synctex.gz']
        
        for ext in temp_extensions:
            temp_file = f"{tex_name_without_ext}{ext}"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"清理临时文件失败 {temp_file}: {e}")
    
    def export_proposal(self, output_filename: str = "generated_proposal.tex", compile_pdf: bool = True, specific_file: str = None):
        """
        主函数：导出完整的研究计划
        :param output_filename: 输出文件名 (将在 self.output_dir 中创建, e.g., "proposal_xxxx.tex")
        :param compile_pdf: 是否自动编译生成PDF
        :param specific_file: 指定要处理的Markdown文件名 (在 self.markdown_source_dir 中查找)
        """
        print("开始导出研究计划...")
        
        # 确保TeX/PDF输出目录存在 (e.g., exporter/pdf_output)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 读取模板 (exporter/main.tex)
        try:
            template = self.read_template()
            print("✓ 已读取模板文件")
        except Exception as e:
            print(f"❌ 读取模板文件失败: {e}")
            return None
        
        # 读取Markdown文件 (从 self.markdown_source_dir)
        md_files = self.read_markdown_files(specific_file)
        if not md_files: # 检查是否成功读取到文件
            print(f"警告: 未能从 '{self.markdown_source_dir}' 读取到Markdown文件。")
            return None
        print(f"✓ 已读取 {len(md_files)} 个Markdown文件")
        
        # 提取和转换内容
        print("正在提取和转换内容...")
        try:
            content_map = self.extract_content_by_type(md_files)
            print("✓ 内容提取和转换完成")
        except Exception as e:
            print(f"❌ 内容提取失败: {e}")
            return None
        
        # 填入模板
        filled_template = self.fill_template(template, content_map)
        
        # 构建最终TeX文件的完整输出路径 (e.g., exporter/pdf_output/proposal_xxxx.tex)
        output_tex_basename = os.path.basename(output_filename) # 确保只取文件名
        output_filepath = os.path.join(self.output_dir, output_tex_basename)
        
        # 保存结果到 self.output_dir 目录
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(filled_template)
            print(f"✓ 研究计划已导出到: {output_filepath}")
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
            return None
        
        # 自动编译PDF
        if compile_pdf:
            print("\n开始编译PDF...")
            # 传递TeX文件名 (basename) 和 TeX/PDF输出目录给编译函数
            # tex_filename 应该是 output_tex_basename
            success = self.compile_with_xelatex(output_tex_basename, self.output_dir)
            if success:
                pdf_name = os.path.splitext(output_tex_basename)[0] + ".pdf"
                pdf_path = os.path.join(self.output_dir, pdf_name) # PDF也在output_dir中
                print(f"✅ PDF文件已生成: {pdf_path}")
                return output_filepath, pdf_path
            else:
                print("⚠️ PDF编译失败，但LaTeX文件已成功生成")
                print("您可以手动运行以下命令编译:")
                print(f"cd {self.output_dir}")
                print(f"xelatex {os.path.basename(output_filepath)}")
                return output_filepath, None

        return output_filepath, None

def main():
    """主函数示例"""
    # 创建导出器实例，使用千问大模型
    exporter = ProposalExporter()
    
    # 检查是否有命令行参数指定文件
    import sys
    specific_md_file = None # 重命名以更清晰
    if len(sys.argv) > 1:
        specific_md_file = sys.argv[1]
        # specific_md_file 应该是相对于 markdown_source_dir 的文件名或完整路径
        # 如果是完整路径，read_markdown_files 会处理
        # 如果只是文件名，read_markdown_files 会在 markdown_source_dir 中查找
        print(f"使用指定Markdown文件: {specific_md_file}")
    else:
        print(f"未指定文件，将自动从 '{exporter.markdown_source_dir}' 选择最新的Markdown文件")
    
    # 生成带时间戳的输出TeX文件名 (将在 pdf_output 目录中创建)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_tex_filename = f"proposal_{timestamp}.tex" # 这是最终tex文件的名称
    
    # 导出研究计划并编译PDF
    # specific_file 参数传递给 export_proposal
    result = exporter.export_proposal(output_tex_filename, compile_pdf=True, specific_file=specific_md_file)
    
    if result is None:
        print("❌ 导出失败")
        return
    
    if isinstance(result, tuple):
        tex_file, pdf_file = result
        print(f"\n导出完成！")
        print(f"LaTeX文件: {tex_file}")
        if pdf_file:
            print(f"PDF文件: {pdf_file}")
            print("✅ 所有文件已成功生成！")
            
            # 尝试打开PDF文件
            try:
                import platform
                if platform.system() == "Linux":
                    subprocess.run(['xdg-open', pdf_file], check=False)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(['open', pdf_file], check=False)
                elif platform.system() == "Windows":
                    subprocess.run(['start', pdf_file], shell=True, check=False)
            except:
                print(f"请手动打开PDF文件: {pdf_file}")
        else:
            print("⚠️ LaTeX文件已生成，但PDF编译失败")
            print("请检查LaTeX环境配置")
    else:
        print(f"\n导出完成！生成的文件: {result}")

if __name__ == "__main__":
    # Api_key = os.getenv('DASHSCOPE_API_KEY')
    # print(Api_key)
    main()
