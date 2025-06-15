import os
import re
import glob
import subprocess
from datetime import datetime
from typing import Dict, List
import json
import shutil
import logging
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import time

load_dotenv()
Api_key = os.getenv('DASHSCOPE_API_KEY')
base_url = os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
    ],
    force=True # 强制覆盖任何已存在的配置
)


class ProposalExporter:
    def __init__(self, api_key: str = None, base_url: str = None):
        """
        初始化导出器
        :param api_key: 千问API密钥
        :param base_url: API基础URL
        """
        # 使用千问大模型配置，与graph.py保持一致
        # Prioritize passed api_key, then environment variable, then None
        effective_api_key = api_key if api_key is not None else os.getenv('DASHSCOPE_API_KEY')
        effective_base_url = base_url if base_url is not None else os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')

        if not effective_api_key:
            logging.error("API key is not set. Please provide it as a parameter or set DASHSCOPE_API_KEY environment variable.")
            # Decide how to handle this: raise error, or allow LLM to be None and handle downstream
            # For now, let's allow it to proceed, ChatOpenAI will raise error if key is truly needed and missing

        self.llm = ChatOpenAI(
            api_key=effective_api_key,
            model="qwen-turbo-latest", 
            base_url=effective_base_url,
            temperature=0,
            # max_tokens=4000  # 限制输出长度，避免超出模型限制
        )
        
        self.template_path = "exporter/main.tex"
        self.markdown_source_dir = "output"  # Markdown文件的源目录
        self.output_dir = "exporter/pdf_output"       # TeX/PDF的输出目录
        self.exporter_dir = "exporter"       # exporter目录路径 (包含cls, main.tex, figures)
        self.references_data: List[Dict] = None # Added to store parsed references

        # Directories for Mermaid processing
        self.final_mermaid_images_dir = os.path.join(self.output_dir, "figures", "mermaid_images")
        self.temp_mermaid_files_dir = os.path.join(self.output_dir, "temp_mermaid") # Temp files in pdf_output
        # Ensure these directories exist
        os.makedirs(self.output_dir, exist_ok=True) # pdf_output
        os.makedirs(self.final_mermaid_images_dir, exist_ok=True) # exporter/pdf_output/figures/mermaid_images
        os.makedirs(self.temp_mermaid_files_dir, exist_ok=True) # exporter/pdf_output/temp_mermaid
        
    def _escape_latex(self, text: str) -> str:
        """Escapes special LaTeX characters in a string."""
        if not text: return ""
        conv = {
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
            '\\': r'\textbackslash{}',
            '<': r'\textless{}',
            '>': r'\textgreater{}',
        }
        regex = re.compile('|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key = lambda item: - len(item))))
        return regex.sub(lambda match: conv[match.group()], text)

    def read_template(self) -> str:
        """读取LaTeX模板文件"""
        with open(self.template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def read_markdown_files(self, specific_file: str = None) -> Dict[str, str]:
        """
        读取Markdown文件并尝试加载对应的参考文献JSON文件
        :param specific_file: 指定文件名，如果为None则自动选择最新文件
        """
        md_files = {}
        selected_md_filepath = None
        
        if specific_file:
            # 读取指定文件
            file_path = os.path.join(self.markdown_source_dir, specific_file) # 使用 markdown_source_dir
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    md_files[specific_file] = content
                logging.info(f"✓ 读取指定文件: {file_path}")
                selected_md_filepath = file_path
            else:
                logging.warning(f"⚠️ 指定文件不存在: {file_path}")
        else:
            # 自动选择最新文件
            pattern = os.path.join(self.markdown_source_dir, "Research_Proposal_*.md") # More specific pattern
            all_md_files = glob.glob(pattern)
            
            if all_md_files:
                # 按修改时间排序，选择最新的文件
                latest_file = max(all_md_files, key=os.path.getmtime)
                filename = os.path.basename(latest_file)
                
                with open(latest_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    md_files[filename] = content
                
                logging.info(f"✓ 自动选择最新文件: {latest_file}")
                logging.debug(f"  文件修改时间: {datetime.fromtimestamp(os.path.getmtime(latest_file))}")
                selected_md_filepath = latest_file
            else:
                logging.warning(f"⚠️ 在目录 '{self.markdown_source_dir}' 中未找到任何符合 'Research_Proposal_*.md' 格式的Markdown文件")

        if selected_md_filepath:
            self._load_references_json(selected_md_filepath)
        
        return md_files

    def _load_references_json(self, md_filepath: str):
        """
        根据Markdown文件路径加载对应的参考文献JSON文件。
        """
        md_basename = os.path.basename(md_filepath)
        if md_basename.startswith("Research_Proposal_"):
            # Construct reference JSON filename: References_Topic_timestamp_uuid.json
            # Example: Research_Proposal_LLM_A_..._uuid.md -> References_LLM_A_..._uuid.json
            ref_json_basename = md_basename.replace("Research_Proposal_", "References_", 1)
            ref_json_basename = os.path.splitext(ref_json_basename)[0] + ".json" # Ensure .json extension
            
            ref_json_filepath = os.path.join(self.markdown_source_dir, ref_json_basename)
            
            if os.path.exists(ref_json_filepath):
                try:
                    with open(ref_json_filepath, 'r', encoding='utf-8') as f:
                        self.references_data = json.load(f)
                    logging.info(f"✓ 成功加载参考文献文件: {ref_json_filepath}")
                except json.JSONDecodeError:
                    logging.warning(f"⚠️ 解析参考文献JSON文件失败: {ref_json_filepath}")
                    self.references_data = None
                except Exception as e:
                    logging.error(f"⚠️ 读取参考文献文件时出错: {ref_json_filepath}, Error: {e}")
                    self.references_data = None
            else:
                logging.info(f"ℹ️ 未找到对应的参考文献文件: {ref_json_filepath}")
                self.references_data = None
        else:
            logging.info(f"ℹ️ Markdown文件名 '{md_basename}' 不符合预期的 'Research_Proposal_' 前缀，跳过加载参考文献。")
            self.references_data = None

    def _escape_latex(self, text: str) -> str:
        """Escapes special LaTeX characters in a string."""
        if not isinstance(text, str):
            return ""
        # Order matters
        text = text.replace('\\', r'\textbackslash{}')
        text = text.replace('{', r'\{')
        text = text.replace('}', r'\}')
        text = text.replace('_', r'\_')
        text = text.replace('^', r'\^{}')
        text = text.replace('&', r'\&')
        text = text.replace('%', r'\%')
        text = text.replace('$', r'\$')
        text = text.replace('#', r'\#')
        text = text.replace('~', r'\textasciitilde{}')
        return text

    def _format_single_reference_to_latex(self, ref: Dict) -> str:
        """Formats a single reference dictionary to a LaTeX \bibitem content string."""
        item_text = ""
        ref_type = ref.get("type", "Unknown")

        title = self._escape_latex(ref.get("title", "N.T."))
        authors_list = ref.get("authors", [])
        authors_str = self._escape_latex(", ".join(authors_list) if authors_list else "N.A.")

        if ref_type == "ArXiv":
            arxiv_id = self._escape_latex(ref.get("arxiv_id", ""))
            published = self._escape_latex(ref.get("published", ""))
            # summary = self._escape_latex(ref.get("summary", "")) # Summary usually not in bib item
            item_text = f"{authors_str}. {title}. arXiv:{arxiv_id} ({published})."
        elif ref_type == "CrossRef":
            journal = self._escape_latex(ref.get("journal", ""))
            published = self._escape_latex(ref.get("published", ""))
            doi = self._escape_latex(ref.get("doi", ""))
            item_text = f"{authors_str}. {title}. {journal} ({published}). DOI: {doi}."
        elif ref_type == "Web":
            url = ref.get("url", "") # Do not escape URL, pass to \url{}
            # Access date might be missing, graph.py generates it on the fly.
            # For now, we'll just use the URL.
            item_text = f"{title}. URL: \\url{{{url}}}"
        else:
            item_text = f"{self._escape_latex(ref.get('title', 'N.T.'))} (Unknown Type)"
        
        return item_text

    def _generate_latex_bibliography(self) -> str:
        """Generates the full LaTeX bibliography section."""
        if not self.references_data:
            return ""

        latex_bib = "" 

        # 使用 \chapter* 以匹配文档其他主要部分的层级
        # latex_bib += "\\chapter*{参考文献}\n"
        # 手动将"参考文献"添加到目录中
        # 第一个参数 'toc' 指的是目录文件
        # 第二个参数 'chapter' 指的是条目的层级（与\chapter一致）
        # 第三个参数 '参考文献' 是显示在目录中的文本
        latex_bib += "\\addcontentsline{toc}{chapter}{参考文献}\n" 
        
        # Determine the widest label for thebibliography environment
        widest_label = "9"
        if self.references_data:
            max_id = 0
            for ref_item in self.references_data:
                if isinstance(ref_item.get("id"), int) and ref_item.get("id") > max_id:
                    max_id = ref_item.get("id")
            if max_id > 9:
                widest_label = "99"
            if max_id > 99:
                widest_label = "999"

        latex_bib += f"\\begin{{thebibliography}}{{{widest_label}}}\n"
        latex_bib += "  \\setlength{\\itemsep}{0pt} % Optional: to reduce space between items\n"


        # Sort references by ID to ensure they match the [1], [2] order
        sorted_references = sorted(self.references_data, key=lambda x: x.get('id', float('inf')))

        for ref in sorted_references:
            # The \bibitem command will be numbered automatically by LaTeX.
            # The key for \bibitem{key} is not strictly needed if we don't \cite{key}
            # but it's good practice to have one. Using 'ref' + id.
            # However, since markdown citations are [1], [2], etc., the order is key.
            # The default numbering of thebibliography will match this if items are ordered.
            item_content = self._format_single_reference_to_latex(ref)
            latex_bib += f"  \\bibitem{{{ref.get('id', '')}}} {item_content}\n"

        latex_bib += "\\end{thebibliography}\n"
        return latex_bib
    
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
                title = re.sub(r'^[#+]\s*', '', line.strip())
                # 清理标题，移除特殊字符和编号
                title = re.sub(r'：.*$', '', title)  # 移除冒号后的内容
                title = re.sub(r'研究计划书[：:]?\s*', '', title)  # 秼除"研究计划书："
                # 如果清理后的标题太短或为空，尝试提取冒号后的内容
                if len(title.strip()) < 3:
                    # 重新提取，这次保留冒号后的内容
                    original_line = re.sub(r'^[#+]\s*', '', line.strip())
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
            logging.error(f"提取标题失败: {e}")
            return "人工智能在医疗领域的应用研究"

    def convert_md_to_latex(self, markdown_content: str, section_type: str) -> str:
        """
        使用大模型将Markdown内容转换为LaTeX格式
        :param markdown_content: Markdown格式的内容
        :param section_type: 章节类型（如"引言"、"文献综述"等）
        :return: 转换后的LaTeX内容
        """
        # 截断内容以避免超出模型限制
        truncated_content = self.truncate_content(markdown_content, 60000)
        
        prompt = f"""
请将以下Markdown内容转换为LaTeX格式，用于学术论文的{section_type}部分。要求：

1. 内容只能填入[]占位符中
2. 严格保持原文内容不变，只转换格式标记
3. 格式转换规则：
   - 将 **文本** 转换为 \\textbf{{文本}}
   - 将 *文本* 转换为 \\textit{{文本}}
   - 将 ## 标题 转换为 \\subsection{{标题}}
   - 将 ### 标题 转换为 \\subsubsection{{标题}}
   - 将 #### 标题 转换为 \\paragraph{{标题}}
   - 保持引用格式 [数字] 不变
   - 保持图片相关的LaTeX代码（如\\begin{{figure}}...\\end{{figure}}）不变
4. 段落格式：
   - 每个段落之间保留一个空行
   - 确保中文排版正确
5. 其他要求：
   - 不要生成任何 \\chapter、\\section 等命令
   - 不要修改原文中的任何文字内容
   - 不要添加任何额外的内容
   - 最多返回2000字的内容
   - 直接返回LaTeX内容，不要使用```latex```或其他代码块标记包裹
   - 确保清理所有Markdown格式符号，包括：
     * 删除所有 **** 加粗符号
     * 删除所有 ** 加粗符号
     * 删除所有 * 斜体符号
     * 删除所有 # 标题符号
     * 删除所有 - 列表符号
     * 删除所有 > 引用符号
     * 删除所有 ` 代码块符号
     * 删除所有 ``` 代码块符号
     * 删除所有 [] 链接符号
     * 删除所有 () 链接符号
     * 删除所有 | 表格符号
     * 删除所有 --- 分隔线符号
   - 特别要求：
     * 删除所有中文数字编号（如"一、"、"二、"等）
     * 删除所有阿拉伯数字编号（如"1."、"2."等）
     * 删除所有带括号的编号（如"（一）"、"（1）"等）
     * 删除所有带点的编号（如"1.1"、"1.2"等）
     * 删除所有带顿号的编号（如"一、"、"二、"等）

Markdown内容：
{truncated_content}

请只返回转换后的纯LaTeX内容，不要包含任何代码块标记，不要包含任何章节标题：
"""
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            response = self.llm.invoke([
                SystemMessage(content="你是一个专业的LaTeX格式转换助手。请严格按照要求转换格式，保持原文内容不变。对于图片相关的LaTeX代码，请保持原样。确保清理所有Markdown格式符号和编号。"),
                HumanMessage(content=prompt)
            ])
            
            latex_content = response.content.strip()
            
            # 清理提取出的内容
            # 1. 移除所有章节标题命令
            latex_content = re.sub(r'\\chapter\{.*?\}', '', latex_content)
            latex_content = re.sub(r'\\section\{.*?\}', '', latex_content)
            
            # 2. 移除所有Markdown标题标记
            latex_content = re.sub(r'^\s*#+\s*.*$', '', latex_content, flags=re.MULTILINE)
            
            # 3. 确保段落之间有适当的空行
            latex_content = re.sub(r'\n{3,}', '\n\n', latex_content)
            
            # 4. 清理所有Markdown格式符号
            latex_content = re.sub(r'\*\*\*(.*?)\*\*\*', r'\1', latex_content)  # 删除 *** 加粗符号
            latex_content = re.sub(r'\*\*(.*?)\*\*', r'\1', latex_content)      # 删除 ** 加粗符号
            latex_content = re.sub(r'\*(.*?)\*', r'\1', latex_content)          # 删除 * 斜体符号
            latex_content = re.sub(r'^\s*[-*+]\s+', '', latex_content, flags=re.MULTILINE)  # 删除列表符号
            latex_content = re.sub(r'^\s*>\s+', '', latex_content, flags=re.MULTILINE)      # 删除引用符号
            latex_content = re.sub(r'`(.*?)`', r'\1', latex_content)            # 删除 ` 代码块符号
            latex_content = re.sub(r'```.*?```', '', latex_content, flags=re.DOTALL)  # 删除 ``` 代码块符号
            latex_content = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', latex_content)   # 删除链接符号
            latex_content = re.sub(r'\|.*?\|', '', latex_content)               # 删除表格符号
            latex_content = re.sub(r'^\s*---+\s*$', '', latex_content, flags=re.MULTILINE)  # 删除分隔线符号
            
            # 5. 清理所有编号
            latex_content = re.sub(r'^[一二三四五六七八九十]+[、.．。]', '', latex_content, flags=re.MULTILINE)  # 删除中文数字编号
            latex_content = re.sub(r'^[（(][一二三四五六七八九十]+[）)]', '', latex_content, flags=re.MULTILINE)  # 删除带括号的中文数字编号
            latex_content = re.sub(r'^\d+[、.．。]', '', latex_content, flags=re.MULTILINE)  # 删除阿拉伯数字编号
            latex_content = re.sub(r'^[（(]\d+[）)]', '', latex_content, flags=re.MULTILINE)  # 删除带括号的阿拉伯数字编号
            latex_content = re.sub(r'^\d+\.\d+[、.．。]', '', latex_content, flags=re.MULTILINE)  # 删除带点的编号
            
            return latex_content.strip()
        except Exception as e:
            logging.error(f"转换失败: {e}")
            # 如果转换失败，返回一个基本的LaTeX表示
            escaped_markdown = self._escape_latex(markdown_content)
            return f"% ---- Fallback for section: {section_type} ----\n{escaped_markdown}\n% ---- End fallback ----"

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
特别注意：
1. 当提取"总结"部分时，请确保内容主要对应研究的最终结论、成果总结、未来展望。
2. 只提取明确标记为"总结"、"结论"、"展望"、"最终总结"等末尾章节的内容。
3. 不要包含研究内容、研究方法等主体部分的详细内容。
4. 如果原文包含以下子标题，请按以下优先级提取：
   - "最终总结"或"结论"（最高优先级）
   - "研究展望"或"未来展望"
   - "预期成果"
5. 如果发现内容与研究内容部分重复，请只保留总结性的表述。
6. 确保提取的内容是总结性的，而不是详细的研究过程描述。
"""
        elif section_name == "研究内容":
            prompt_text += """
特别注意：当提取"研究内容"部分时，请确保内容主要对应研究方法、研究设计、数据来源、分析工具等具体的研究实施方案。
请重点查找标题为"研究设计"、"研究方法"、"数据和来源"、"方法和分析"、"活动和工作流程"等章节的内容。
不要包含引言、文献综述等前文内容，只提取与具体研究实施相关的部分。
"""
        elif section_name == "引言":
            prompt_text += """
特别注意：当提取"引言"部分时，请确保只提取 Markdown 文件中以 `# 引言` (或类似的一级标题，如 `# Introduction`) 开头的章节内容。
你需要完整地提取该章节下的所有文本，直到遇到下一个一级或二级标题为止。
不要包含摘要、目录、文献综述或研究计划的其他部分。
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
            logging.error(f"提取{section_name}内容失败: {e}")
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
            '参考文献内容': '', # New placeholder for bibliography
            'time': datetime.now().strftime('%Y年%m月')
        }
        
        # 合并所有Markdown内容
        all_content = '\n\n'.join(md_files.values())
        logging.info(f"总内容长度: {len(all_content)} 字符")
        
        # 提取标题
        title_content = self.extract_title(all_content)
        if title_content:
            content_map['title'] = title_content
            logging.info(f"✓ 提取标题: {title_content}")
        
        # 使用大模型分析和提取内容
        for section in ['引言', '文献综述', '研究内容', '总结']:
            logging.info(f"正在提取 {section} 内容...")
            section_content = self.extract_section_content(all_content, section)
            if section_content:
                logging.info(f"✓ 提取到 {section} 内容，长度: {len(section_content)} 字符")
                logging.info(f"正在转换 {section} 为LaTeX格式...")
                latex_content = self.convert_md_to_latex(section_content, section)
                content_map[section] = latex_content
                logging.info(f"✓ {section} 转换完成")
            else:
                logging.warning(f"⚠️ 未找到 {section} 相关内容")
        
        # Generate LaTeX bibliography
        logging.info("正在生成参考文献部分...")
        bibliography_latex = self._generate_latex_bibliography()
        if bibliography_latex:
            content_map['参考文献内容'] = bibliography_latex
            logging.info(f"✓ 参考文献部分生成完成, 长度: {len(bibliography_latex)} 字符")
        else:
            logging.info("ℹ️ 未生成参考文献部分 (无数据或错误)")
            
        return content_map
    
    def _process_all_mermaid_diagrams(self, markdown_content: str, report_filename_base: str) -> str:
        """
        处理所有Mermaid图表：
        1. 提取Mermaid代码块
        2. 将每个Mermaid代码块保存为单独的md文件
        3. 使用mmdc工具将md文件转换为图片
        4. 在LaTeX中插入生成的图片
        """
        logging.info("开始处理所有Mermaid图表...")
        
        processed_content = markdown_content
        # 改进Mermaid代码块匹配模式，使其更严格
        mermaid_matches = list(re.finditer(r"```mermaid\s*([\s\S]+?)```", markdown_content))
        
        if not mermaid_matches:
            logging.info("未找到Mermaid图表。")
            return markdown_content

        num_diagrams = len(mermaid_matches)
        logging.info(f"找到 {num_diagrams} 个Mermaid图表需要处理。")

        for idx, match in enumerate(mermaid_matches):
            original_mermaid_block = match.group(0)
            mermaid_code = match.group(1).strip()
            
            # 为每个图表创建唯一的标识符
            image_file_stem = f"{report_filename_base}_mermaid_{idx}"
            temp_md_filename = f"{image_file_stem}.md"
            output_png_filename = f"{image_file_stem}.png"

            # 创建临时md文件路径和最终图片路径
            temp_md_filepath = os.path.join(self.temp_mermaid_files_dir, temp_md_filename)
            output_png_filepath = os.path.join(self.final_mermaid_images_dir, output_png_filename)

            logging.info(f"处理Mermaid图表 {idx + 1}/{num_diagrams}: {image_file_stem}")

            try:
                # 将Mermaid代码保存为单独的md文件
                with open(temp_md_filepath, "w", encoding="utf-8") as mf:
                    mf.write("```mermaid\n")
                    mf.write(mermaid_code)
                    mf.write("\n```")
                logging.debug(f"已创建临时Mermaid md文件: {temp_md_filepath}")

                # 先将临时md文件复制到图片目录
                target_md_in_img_dir = os.path.join(self.final_mermaid_images_dir, temp_md_filename)
                shutil.copy(temp_md_filepath, target_md_in_img_dir)

                # 使用mmdc工具将md文件转换为图片（只用文件名，cwd为图片目录）
                mmdc_command = [
                    "mmdc",
                    "-i", temp_md_filename,  # 只用文件名
                    "-o", output_png_filename,  # 只用文件名
                    "-w", "1024",
                    "-H", "768",
                    "--backgroundColor", "white"
                ]
                logging.debug(f"执行mmdc命令: {' '.join(mmdc_command)}，工作目录: {self.final_mermaid_images_dir}")
                process = subprocess.run(
                    mmdc_command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=60,
                    cwd=self.final_mermaid_images_dir  # 强制在目标目录下生成
                )

                # 清理复制到图片目录下的md文件
                if os.path.exists(target_md_in_img_dir):
                    try:
                        os.remove(target_md_in_img_dir)
                        logging.debug(f"已删除图片目录下的临时md文件: {target_md_in_img_dir}")
                    except OSError as e_rm:
                        logging.warning(f"无法删除图片目录下的临时md文件 {target_md_in_img_dir}: {e_rm}")

                if process.returncode == 0:
                    # 检查图片是否生成在预期位置（支持 -1 后缀）
                    found_png = None
                    for _ in range(5):  # 最多重试5次
                        if os.path.exists(output_png_filepath):
                            found_png = output_png_filepath
                            break
                        # 查找以 image_file_stem 开头的 png 文件（包括 -1 后缀）
                        for fname in os.listdir(self.final_mermaid_images_dir):
                            if fname.startswith(image_file_stem) and fname.endswith('.png'):
                                found_png = os.path.join(self.final_mermaid_images_dir, fname)
                                break
                        if found_png:
                            break
                        time.sleep(0.2)  # 等待写盘
                    if found_png:
                        logging.info(f"✅ Mermaid PNG生成成功: {found_png}")
                    else:
                        # 输出目录下所有png文件名
                        all_pngs = [f for f in os.listdir(self.final_mermaid_images_dir) if f.endswith('.png')]
                        logging.error(f"⚠️ 无法找到生成的PNG文件: {output_png_filepath} 或 {image_file_stem}-1.png。当前目录下PNG文件: {all_pngs}")
                    
                    # 构建LaTeX中的图片路径（相对于main.tex）
                    latex_image_path = os.path.join("figures", "mermaid_images", output_png_filename)
                    latex_image_path = latex_image_path.replace("\\", "/")  # 确保使用正斜杠

                    # 尝试从mermaid代码中提取标题作为图片说明
                    caption_text = f"Mermaid图表 {idx + 1}"  # 默认说明
                    title_match = re.search(r"^\s*title\s*:\s*(.+)$", mermaid_code, re.MULTILINE | re.IGNORECASE)
                    if title_match:
                        caption_text = self._escape_latex(title_match.group(1).strip())
                    
                    # 创建唯一的标签
                    label_text = f"fig:{image_file_stem.replace('_', '-')}"

                    # 生成LaTeX图片代码
                    latex_code = (
                        f"\n\n\\begin{{figure}}[htbp]\n"
                        f"\\centering\n"
                        f"\\includegraphics[width=0.9\\textwidth]{{{latex_image_path}}}\n"
                        f"\\caption{{{caption_text}}}\n"
                        f"\\label{{{label_text}}}\n"
                        f"\\end{{figure}}\n\n"
                    )
                    
                    # 替换原始Mermaid代码块为LaTeX图片代码
                    processed_content = processed_content.replace(original_mermaid_block, latex_code, 1)
                    logging.debug(f"已将Mermaid代码块 {idx+1} 替换为LaTeX图片代码。")

                else:
                    logging.error(f"⚠️ 生成Mermaid PNG失败: {image_file_stem}")
                    logging.error(f"MMDC返回码: {process.returncode}")
                    logging.error(f"MMDC标准输出: {process.stdout}")
                    logging.error(f"MMDC错误输出: {process.stderr}")
                    error_message = self._escape_latex(f"生成Mermaid图表失败: {image_file_stem}。请检查日志。")
                    processed_content = processed_content.replace(original_mermaid_block, f"\n% {error_message}\n", 1)

            except FileNotFoundError as e:
                logging.error(f"⚠️ 未找到MMDC命令或生成的文件: {e}")
                error_message = self._escape_latex(f"未找到MMDC命令或生成的文件: {image_file_stem}。")
                processed_content = processed_content.replace(original_mermaid_block, f"\n% {error_message}\n", 1)
            except subprocess.TimeoutExpired:
                logging.error(f"⚠️ MMDC命令超时: {image_file_stem}")
                error_message = self._escape_latex(f"生成Mermaid图表超时: {image_file_stem}。")
                processed_content = processed_content.replace(original_mermaid_block, f"\n% {error_message}\n", 1)
            except Exception as e:
                logging.error(f"⚠️ 处理Mermaid图表时发生异常 {image_file_stem}: {e}", exc_info=True)
                error_message = self._escape_latex(f"处理Mermaid图表时发生异常: {image_file_stem} - {str(e)}")
                processed_content = processed_content.replace(original_mermaid_block, f"\n% {error_message}\n", 1)
            finally:
                # 清理临时md文件
                if os.path.exists(temp_md_filepath):
                    try:
                        os.remove(temp_md_filepath)
                        logging.debug(f"已删除临时md文件: {temp_md_filepath}")
                    except OSError as e_rm:
                        logging.warning(f"无法删除临时md文件 {temp_md_filepath}: {e_rm}")
        
        logging.info("已完成所有Mermaid图表的处理。")
        return processed_content

    def fill_template(self, template: str, content_map: Dict[str, str], md_content_for_mermaid: str, report_filename_base: str) -> str:
        """
        将提取的内容填入模板，并处理Mermaid图像
        :param template: LaTeX模板内容
        :param content_map: 包含各章节内容的字典
        :param md_content_for_mermaid: 包含Mermaid图表的Markdown内容
        :param report_filename_base: 报告文件名基础（用于生成图片文件名）
        :return: 填充后的模板内容
        """
        filled_template = template
        
        # 替换标准占位符
        filled_template = filled_template.replace('[title]', content_map.get('title', '研究计划'))
        filled_template = filled_template.replace('[time]', content_map.get('time', datetime.now().strftime('%Y年%m月')))
        filled_template = filled_template.replace('[引言]', content_map.get('引言', ''))
        filled_template = filled_template.replace('[文献综述]', content_map.get('文献综述', ''))
        filled_template = filled_template.replace('[研究内容]', content_map.get('研究内容', ''))
        filled_template = filled_template.replace('[总结]', content_map.get('总结', ''))
        filled_template = filled_template.replace('[参考文献内容]', content_map.get('参考文献内容', ''))
        
        # 查找第一个gantt类型的图片
        gantt_figure_code = ''
        image_file_stem = f"{report_filename_base}_mermaid_0"
        
        # 检查图片目录中是否存在对应的图片文件
        for fname in os.listdir(self.final_mermaid_images_dir):
            if fname.startswith(image_file_stem) and fname.endswith('.png'):
                # 构建LaTeX中的图片路径（相对于main.tex）
                latex_image_path = os.path.join("figures", "mermaid_images", fname)
                latex_image_path = latex_image_path.replace("\\", "/")  # 确保使用正斜杠

                # 生成LaTeX图片代码
                gantt_figure_code = (
                    f"\n\n\\begin{{figure}}[htbp]\n"
                    f"\\centering\n"
                    f"\\includegraphics[width=0.9\\textwidth]{{{latex_image_path}}}\n"
                    f"\\caption{{项目时间规划甘特图}}\n"
                    f"\\label{{fig:gantt}}\n"
                    f"\\end{{figure}}\n\n"
                )
                logging.info(f'✅ 使用已生成的甘特图图片: {fname}')
                break

        # 替换模板中的占位符
        # filled_template = filled_template.replace('%MERMAID_IMAGE%', gantt_figure_code)
        filled_template = filled_template.replace('[Mermaid Image]', gantt_figure_code)
        
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


        logging.info(f"正在使用xelatex编译: {tex_full_path}")

        # 复制 .cls 文件
        cls_source_file = os.path.join(self.exporter_dir, "phdproposal.cls")
        if not os.path.exists(cls_source_file):
            logging.error(f"❌ 找不到类文件: {cls_source_file}")
            return False
        
        import shutil
        target_cls_file = os.path.join(output_dir, "phdproposal.cls")
        try:
            shutil.copy2(cls_source_file, target_cls_file)
            logging.info(f"✓ 已复制类文件到: {target_cls_file}")
        except Exception as e:
            logging.error(f"❌ 复制类文件失败: {e}")
            return False

        # 复制 Logo 文件和 figures 目录
        logo_source_file = os.path.join(self.exporter_dir, "figures", "Logo.png")
        target_figures_dir = os.path.join(output_dir, "figures")
        target_logo_file = os.path.join(target_figures_dir, "Logo.png")

        if os.path.exists(logo_source_file):
            os.makedirs(target_figures_dir, exist_ok=True)
            try:
                shutil.copy2(logo_source_file, target_logo_file)
                logging.info(f"✓ 已复制Logo文件到: {target_logo_file}")
            except Exception as e:
                logging.error(f"❌ 复制Logo文件失败: {e}")
                # 根据需求决定是否在此处返回False，如果Logo是可选的，可以继续
        else:
            logging.warning(f"⚠️ 未找到Logo文件: {logo_source_file}，将不包含Logo。")


        try:
            original_cwd = os.getcwd()
            os.chdir(output_dir) # 切换到编译目录
            logging.debug(f"当前工作目录: {os.getcwd()}")
            logging.debug(f"编译文件: {tex_basename}") # 应该只编译文件名

            result1 = subprocess.run([
                'xelatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                tex_basename
            ], capture_output=True, text=True, timeout=120)

            if result1.returncode != 0:
                logging.error(f"❌ 第一次xelatex编译失败:")
                logging.error(f"标准输出: {result1.stdout}")
                logging.error(f"错误输出: {result1.stderr}")
                log_file = f"{tex_name_without_ext}.log"
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()
                        logging.error(f"Log文件内容:\n{log_content[-1000:]}")
                return False

            logging.info("正在进行第二次编译（处理交叉引用）...")
            result2 = subprocess.run([
                'xelatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                tex_basename
            ], capture_output=True, text=True, timeout=120)

            if result2.returncode != 0:
                logging.error(f"❌ 第二次xelatex编译失败:")
                logging.error(f"错误输出: {result2.stderr}")
                return False

            pdf_filename = f"{tex_name_without_ext}.pdf"
            if os.path.exists(pdf_filename):
                logging.info(f"✅ PDF文件生成成功: {os.path.join(os.getcwd(), pdf_filename)}") # 使用os.getcwd()获取绝对路径
                self._cleanup_temp_files(tex_name_without_ext)
                try:
                    os.remove("phdproposal.cls") # 清理复制的cls文件
                    if os.path.exists(target_figures_dir): # 清理复制的figures目录
                        shutil.rmtree(target_figures_dir)
                    logging.info("✓ 已清理临时类文件和Logo文件")
                except Exception as e:
                    logging.warning(f"⚠️ 清理临时文件失败: {e}")
                return True
            else:
                logging.error("❌ PDF文件未能生成")
                return False

        except subprocess.TimeoutExpired:
            logging.error("❌ xelatex编译超时")
            return False
        except FileNotFoundError:
            logging.error("❌ 未找到xelatex命令，请确保已安装LaTeX环境")
            logging.info("Ubuntu/Debian: sudo apt-get install texlive-full")
            logging.info("CentOS/RHEL: sudo yum install texlive-scheme-full")
            return False
        except Exception as e:
            logging.error(f"❌ 编译过程中发生错误: {e}")
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
                    logging.warning(f"清理临时文件失败 {temp_file}: {e}")
    
    def export_proposal(self, output_filename: str = "generated_proposal.tex", compile_pdf: bool = True, specific_file: str = None):
        """
        主函数：导出完整的研究计划
        :param output_filename: 输出文件名 (将在 self.output_dir 中创建, e.g., "proposal_xxxx.tex")
        :param compile_pdf: 是否自动编译生成PDF
        :param specific_file: 指定要处理的Markdown文件名 (在 self.markdown_source_dir 中查找)
        """
        logging.info("开始导出研究计划...")
        
        # 确保TeX/PDF输出目录存在 (e.g., exporter/pdf_output)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 读取模板 (exporter/main.tex)
        try:
            template = self.read_template()
            logging.info("✓ 已读取模板文件")
        except Exception as e:
            logging.error(f"❌ 读取模板文件失败: {e}")
            return None, None # Return two Nones for tex_file, pdf_file
        
        # 读取Markdown文件 (从 self.markdown_source_dir)
        md_files = self.read_markdown_files(specific_file)
        if not md_files:
            logging.warning(f"警告: 未能从 '{self.markdown_source_dir}' 读取到Markdown文件。")
            return None, None
        logging.info(f"✓ 已读取 {len(md_files)} 个Markdown文件")
        
        # 合并所有Markdown内容，用于Mermaid提取和内容分析
        full_md_content = "\n\n".join(md_files.values())
        
        logging.info("正在提取和转换内容...")
        try:
            content_map = self.extract_content_by_type(md_files) # extract_content_by_type uses md_files dict
            logging.info("✓ 内容提取和转换完成")
        except Exception as e:
            logging.error(f"❌ 内容提取失败: {e}")
            return None, None
        
        # 获取报告文件名基础，用于Mermaid图片命名
        report_filename_base = os.path.splitext(os.path.basename(output_filename))[0]

        # Process all Mermaid diagrams in the entire document before section splitting or LLM conversion
        logging.info("Processing Mermaid diagrams globally before filling template...")
        full_md_content = self._process_all_mermaid_diagrams(full_md_content, report_filename_base)
        logging.info("Global Mermaid diagrams processed and replaced with LaTeX image tags.")
        
        # 填入模板，此时会处理Mermaid图表
        filled_template = self.fill_template(template, content_map, full_md_content, report_filename_base)
        
        output_tex_basename = os.path.basename(output_filename)
        output_filepath = os.path.join(self.output_dir, output_tex_basename)
        
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(filled_template)
            logging.info(f"✓ 研究计划已导出到: {output_filepath}")
        except Exception as e:
            logging.error(f"❌ 保存文件失败: {e}")
            return output_filepath, None # Return tex_file path even if PDF fails later
        
        pdf_path = None
        if compile_pdf:
            logging.info("\n开始编译PDF...")
            success = self.compile_with_xelatex(output_tex_basename, self.output_dir)
            if success:
                pdf_name = os.path.splitext(output_tex_basename)[0] + ".pdf"
                pdf_path = os.path.join(self.output_dir, pdf_name)
                logging.info(f"✅ PDF文件已生成: {pdf_path}")
            else:
                logging.warning("⚠️ PDF编译失败，但LaTeX文件已成功生成")
                logging.info(f"您可以手动运行以下命令编译: cd {self.output_dir} && xelatex {output_tex_basename}")
        
        return output_filepath, pdf_path

# 全局的 convert_to_latex 函数不再需要，其逻辑已移入 ProposalExporter
# def convert_to_latex(md_content, research_field, output_dir, report_filename_base):
# ...

def main():
    """主函数示例"""
    exporter = ProposalExporter()
    
    import sys
    specific_md_file = None
    if len(sys.argv) > 1:
        specific_md_file = sys.argv[1]
        logging.info(f"使用指定Markdown文件: {specific_md_file}")
    else:
        logging.info(f"未指定文件，将自动从 '{exporter.markdown_source_dir}' 选择最新的Markdown文件")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 尝试从文件名提取研究领域部分，如果失败则使用通用名称
    # This part is tricky if specific_md_file is None or doesn't follow the pattern
    research_field_for_filename = "proposal" 
    temp_md_files = exporter.read_markdown_files(specific_md_file) # Read once to get filename if auto
    if temp_md_files:
        # Assuming temp_md_files has one entry if specific_file is None and a file is found
        # Or if specific_file is provided and valid.
        first_filename = list(temp_md_files.keys())[0]
        match = re.search(r'Research_Proposal_([^_]+(?:_[^_]+)*)_proposal', first_filename)
        if match:
            research_field_for_filename = match.group(1)
        else: # Fallback if pattern doesn't match
            research_field_for_filename = os.path.splitext(first_filename)[0].replace("Research_Proposal_", "").replace("_proposal", "")[:30]
    
    output_tex_filename = f"{research_field_for_filename}_{timestamp}.tex"
    
    logging.info(f"🔄 正在导出研究计划为 {output_tex_filename} 并编译PDF...")
    # 调用 exporter.export_proposal，它现在内部处理Mermaid
    tex_file_path, pdf_file_path = exporter.export_proposal(
        output_filename=output_tex_filename,
        compile_pdf=True,
        specific_file=specific_md_file
    )
    
    if tex_file_path:
        logging.info(f"\n导出完成！")
        logging.info(f"LaTeX文件: {tex_file_path}")
        if pdf_file_path:
            logging.info(f"PDF文件: {pdf_file_path}")
            logging.info("✅ 所有文件已成功生成！")
            try:
                import platform
                if platform.system() == "Linux":
                    subprocess.run(['xdg-open', pdf_file_path], check=False)
                elif platform.system() == "Darwin":
                    subprocess.run(['open', pdf_file_path], check=False)
                elif platform.system() == "Windows":
                    subprocess.run(['start', pdf_file_path], shell=True, check=False)
            except Exception as e:
                logging.error(f"无法自动打开PDF文件: {e}. 请手动打开: {pdf_file_path}")
        else:
            logging.warning("⚠️ LaTeX文件已生成，但PDF编译失败。请检查LaTeX环境配置。")
    else:
        logging.error("❌ 导出失败。")

if __name__ == "__main__":
    # 配置日志记录
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main()
