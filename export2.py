import os
import re
import glob
import subprocess
from datetime import datetime
from typing import Dict, List, Optional
import json
import shutil
import logging
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import time
from backend.src.utils.queue_util import QueueUtil
from backend.src.entity.stream_mes import StreamAnswerMes
import sys
from openai import OpenAI
from langchain.schema import SystemMessage, HumanMessage
import argparse

load_dotenv()
Api_key = os.getenv('DASHSCOPE_API_KEY')
base_url = os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 明确指定输出到stdout
    ],
    force=True # 强制覆盖任何已存在的配置
)

# 添加一个根日志记录器
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 确保日志输出不被缓冲
sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+

class ProposalExporter:
    def __init__(self, api_key: str = None, base_url: str = None, proposal_id: str = None):
        """
        初始化导出器
        :param api_key: 千问API密钥
        :param base_url: API基础URL
        :param proposal_id: 提案ID，用于发送消息
        """
        # 优先使用传入的参数，其次使用环境变量
        self.api_key = api_key if api_key is not None else os.getenv('DASHSCOPE_API_KEY')
        self.base_url = base_url if base_url is not None else os.getenv('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        self.proposal_id = proposal_id
        
        if not self.api_key:
            raise ValueError("API key is not set. Please provide it as a parameter or set DASHSCOPE_API_KEY environment variable.")
            
        self.llm = ChatOpenAI(
            api_key=self.api_key,
            model="qwen-plus",
            base_url=self.base_url,
            temperature=0,
            streaming=True,
        )
        
        # 设置导出步骤，使用更高的初始值
        self.export_step = 100
        
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 设置各种路径
        self.template_path = os.path.join(current_dir, "exporter", "main.tex")
        self.markdown_source_dir = os.path.join(current_dir, "output")  # Markdown文件的源目录
        self.output_dir = os.path.join(current_dir, "exporter", "pdf_output")  # TeX/PDF的输出目录
        self.exporter_dir = os.path.join(current_dir, "exporter")  # exporter目录路径
        
        # 确保目录存在
        os.makedirs(self.markdown_source_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 检查模板文件是否存在
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"找不到LaTeX模板文件: {self.template_path}")
            
        logging.info(f"✓ 使用模板文件: {self.template_path}")
        logging.info(f"✓ Markdown源目录: {self.markdown_source_dir}")
        logging.info(f"✓ PDF输出目录: {self.output_dir}")
        
        self.references_data: List[Dict] = None  # 存储解析后的参考文献

        # Directories for Mermaid processing
        self.final_mermaid_images_dir = os.path.join(self.output_dir, "figures", "mermaid_images")
        self.temp_mermaid_files_dir = os.path.join(self.output_dir, "temp_mermaid")
        
        # 确保这些目录存在
        os.makedirs(self.final_mermaid_images_dir, exist_ok=True)
        os.makedirs(self.temp_mermaid_files_dir, exist_ok=True)

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
        """读取Markdown文件内容"""
        md_files = {}
        
        try:
            if specific_file:
                # 如果指定了特定文件，确保使用完整路径
                if not os.path.isabs(specific_file):
                    specific_file = os.path.join(self.markdown_source_dir, specific_file)
                if not os.path.exists(specific_file):
                    raise FileNotFoundError(f"找不到指定的Markdown文件: {specific_file}")
                md_files[specific_file] = self._read_file(specific_file)
                logging.info(f"✓ 成功读取指定文件: {specific_file}")
            else:
                # 读取目录中的所有md文件
                for filename in os.listdir(self.markdown_source_dir):
                    if filename.endswith('.md'):
                        filepath = os.path.join(self.markdown_source_dir, filename)
                        md_files[filepath] = self._read_file(filepath)
                        logging.info(f"✓ 已读取文件: {filename}")
                
                if not md_files:
                    raise FileNotFoundError(f"在目录 {self.markdown_source_dir} 中未找到任何Markdown文件")
                
                # 获取最新的文件
                latest_file = max(md_files.keys(), key=lambda x: os.path.getmtime(x))
                logging.info(f"✓ 自动选择最新文件: {latest_file}")
            
            return md_files
            
        except Exception as e:
            logging.error(f"❌ 读取Markdown文件时发生错误: {str(e)}")
            raise

    def _load_references_json(self, md_filepath: str):
        """加载参考文献JSON文件"""
        try:
            # 从Markdown文件路径中提取ID
            filename = os.path.basename(md_filepath)
            if filename.startswith("Research_Proposal_"):
                proposal_id = filename.replace("Research_Proposal_", "").replace(".md", "")
            else:
                proposal_id = os.path.splitext(filename)[0]
            
            # 首先在output目录下查找
            ref_filepath = os.path.join("output", f"References_{proposal_id}.json")
            if not os.path.exists(ref_filepath):
                # 如果不存在，尝试在markdown_source_dir下查找
                ref_filepath = os.path.join(self.markdown_source_dir, f"References_{proposal_id}.json")
            
            if os.path.exists(ref_filepath):
                with open(ref_filepath, 'r', encoding='utf-8') as f:
                    self.references_data = json.load(f)
                logging.info(f"✓ 成功加载参考文献文件: {ref_filepath}")
                logging.info(f"ℹ️ 加载了 {len(self.references_data)} 条参考文献")
            else:
                logging.warning(f"⚠️ 未找到参考文献文件: {ref_filepath}")
                self.references_data = []
                
        except Exception as e:
            logging.error(f"❌ 加载参考文献文件时发生错误: {str(e)}")
            self.references_data = []

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
        """生成LaTeX格式的参考文献部分"""
        if not self.references_data:
            logging.warning("ℹ️ 未生成参考文献部分 (无数据或错误)")
            return ""
            
        try:
            bib_items = []
            for ref in self.references_data:
                try:
                    # 提取作者信息
                    authors = []
                    if 'author' in ref:
                        if isinstance(ref['author'], list):
                            authors = [author.get('name', '') for author in ref['author']]
                        elif isinstance(ref['author'], str):
                            authors = [ref['author']]
                    
                    # 提取标题
                    title = ref.get('title', '')
                    
                    # 提取年份
                    year = ref.get('year', '')
                    
                    # 提取期刊/会议名称
                    venue = ref.get('venue', '')
                    if not venue:
                        venue = ref.get('journal', '')
                    
                    # 提取DOI
                    doi = ref.get('doi', '')
                    
                    # 构建参考文献条目
                    bib_item = f"\\bibitem{{{ref.get('id', '')}}} "
                    if authors:
                        bib_item += f"{', '.join(authors)}. "
                    if title:
                        bib_item += f"\\textit{{{self._escape_latex(title)}}}. "
                    if venue:
                        bib_item += f"{self._escape_latex(venue)}. "
                    if year:
                        bib_item += f"({year}). "
                    if doi:
                        bib_item += f"DOI: {doi}"
                    
                    bib_items.append(bib_item)
                    
                except Exception as e:
                    logging.warning(f"⚠️ 处理参考文献条目时出错: {str(e)}")
                    continue
            
            if not bib_items:
                logging.warning("ℹ️ 未生成参考文献部分 (无有效条目)")
                return ""
            
            # 生成完整的参考文献部分
            bibliography = "\\begin{thebibliography}{99}\n"
            bibliography += "\n".join(bib_items)
            bibliography += "\n\\end{thebibliography}"
            
            logging.info(f"✓ 成功生成参考文献部分，包含 {len(bib_items)} 条引用")
            return bibliography
            
        except Exception as e:
            logging.error(f"❌ 生成参考文献部分时发生错误: {str(e)}")
            return ""
    
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
        """简单的Markdown到LaTeX转换"""
        # 处理表格
        def convert_table(match):
            table_content = match.group(1)
            lines = table_content.strip().split('\n')
            
            # 处理表头
            header = lines[0].strip('|').split('|')
            header = [h.strip() for h in header]
            
            # 处理分隔行
            separator = lines[1].strip('|').split('|')
            separator = [s.strip() for s in separator]
            
            # 处理数据行
            data_rows = []
            for line in lines[2:]:
                if line.strip():
                    cells = line.strip('|').split('|')
                    cells = [cell.strip() for cell in cells]
                    data_rows.append(cells)
            
            # 构建LaTeX表格
            latex_table = "\\begin{table}[htbp]\n\\centering\n\\begin{tabular}{" + "|c" * len(header) + "|}\n\\hline\n"
            
            # 添加表头
            latex_table += " & ".join(header) + " \\\\\n\\hline\n"
            
            # 添加数据行
            for row in data_rows:
                latex_table += " & ".join(row) + " \\\\\n\\hline\n"
            
            latex_table += "\\end{tabular}\n\\end{table}\n"
            return latex_table

        # 转换表格
        table_pattern = r"\|(.*?)\|\n\|(.*?)\|\n(\|.*?\|)"
        markdown_content = re.sub(table_pattern, convert_table, markdown_content, flags=re.DOTALL)
        
        # 处理图片
        image_pattern = r"!\[(.*?)\]\((.*?)\)"
        def convert_image(match):
            alt_text = match.group(1)
            image_path = match.group(2)
            return f"\\begin{{figure}}[htbp]\n\\centering\n\\includegraphics[width=0.8\\textwidth]{{{image_path}}}\n\\caption{{{alt_text}}}\n\\end{{figure}}"
        
        markdown_content = re.sub(image_pattern, convert_image, markdown_content)
        
        return markdown_content

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
4. 表格处理规则：
   - 识别Markdown中的表格（以 | 分隔的文本块）
   - 将表格转换为LaTeX的tabularx环境
   - 对于三列表格，使用以下列宽比例：
     * 第一列：15% 的文本宽度
     * 第二列：25% 的文本宽度
     * 第三列：60% 的文本宽度
   - 对于其他列数的表格，使用X列类型平均分配宽度
   - 表格示例：
     ```latex
     \\begin{{tabularx}}{{\\textwidth}}{{>{{\\hsize=0.15\\hsize}}X >{{\\hsize=0.25\\hsize}}X >{{\\hsize=0.60\\hsize}}X}}
     \\hline
     列1 & 列2 & 列3 \\\\
     \\hline
     内容1 & 内容2 & 内容3 \\\\
     \\hline
     \\end{{tabularx}}
     ```
5. 段落格式：
   - 每个段落之间保留一个空行
   - 确保中文排版正确
6. 其他要求：
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
7. 反斜杠使用规则：
   - 严格禁止在非LaTeX命令中使用反斜杠（\\）
   - 只允许在以下情况使用反斜杠：
     * LaTeX命令中（如 \\textbf、\\textit、\\subsection 等）
     * LaTeX环境中（如 \\begin、\\end 等）
     * LaTeX特殊字符转义（如 \\%、\\$、\\# 等）
   - 如果原文中包含反斜杠，需要：
     * 如果是LaTeX命令，保持原样
     * 如果是普通文本中的反斜杠，需要删除或替换为其他符号
   - 特别注意：
     * 不要在普通文本中使用反斜杠作为分隔符
     * 不要在普通文本中使用反斜杠作为转义字符
     * 不要在普通文本中使用反斜杠作为路径分隔符
     * 严格禁止使用非LaTeX语法的反斜杠，例如：
       - 禁止使用 \\Minecraft、\\CS 等游戏相关缩写
       - 禁止使用 \\Windows、\\Linux 等操作系统名称
       - 禁止使用 \\Python、\\Java 等编程语言名称
       - 禁止使用 \\AI、\\ML 等缩写
       - 禁止使用 \\URL、\\HTTP 等网络相关缩写
       - 禁止使用 \\CPU、\\GPU 等硬件相关缩写
       - 禁止使用 \\API、\\SDK 等软件相关缩写
       - 禁止使用 \\PDF、\\HTML 等文件格式缩写
       - 禁止使用 \\USB、\\HDMI 等接口名称
       - 禁止使用 \\WiFi、\\4G 等网络技术名称
     * 如果遇到这些情况，应该：
       - 删除反斜杠，直接使用原文本（如 "Minecraft" 而不是 "\\Minecraft"）
       - 或者使用适当的LaTeX命令（如 \\texttt{{Minecraft}} 如果需要特殊格式）
       - 或者使用其他合适的表达方式

Markdown内容：
{truncated_content}

请只返回转换后的纯LaTeX内容，不要包含任何代码块标记，不要包含任何章节标题：
"""
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            response = self.llm.invoke([
                SystemMessage(content="你是一个专业的LaTeX格式转换助手。请严格按照要求转换格式，保持原文内容不变。对于图片和表格相关的LaTeX代码，请保持原样。确保清理所有Markdown格式符号和编号。特别注意表格的转换，使用tabularx环境并设置合适的列宽比例。特别注意反斜杠的使用，只在LaTeX命令和环境中使用，严格禁止使用非LaTeX语法的反斜杠。"),
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
            
            # 6. 清理非LaTeX命令中的反斜杠
            # 保留LaTeX命令中的反斜杠
            latex_content = re.sub(r'(?<!\\)\\(?![\w{])', '', latex_content)  # 删除非LaTeX命令中的反斜杠
            
            # 7. 清理特定的非LaTeX语法的反斜杠
            non_latex_patterns = [
                r'\\Minecraft', r'\\CS', r'\\Windows', r'\\Linux',
                r'\\Python', r'\\Java', r'\\AI', r'\\ML',
                r'\\URL', r'\\HTTP', r'\\CPU', r'\\GPU',
                r'\\API', r'\\SDK', r'\\PDF', r'\\HTML',
                r'\\USB', r'\\HDMI', r'\\WiFi', r'\\4G'
            ]
            for pattern in non_latex_patterns:
                latex_content = re.sub(pattern, lambda m: m.group(0)[1:], latex_content)  # 删除反斜杠，保留文本
            
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
        """处理所有mermaid图表"""
        try:
            # 查找所有mermaid代码块
            mermaid_pattern = r"```mermaid\n(.*?)\n```"
            mermaid_blocks = re.finditer(mermaid_pattern, markdown_content, re.DOTALL)
            
            for i, match in enumerate(mermaid_blocks):
                mermaid_code = match.group(1)
                # 生成唯一的文件名
                diagram_filename = f"{report_filename_base}_diagram_{i+1}.png"
                diagram_path = os.path.join(self.output_dir, diagram_filename)
                
                # 将mermaid代码转换为图片
                try:
                    # 使用mmdc命令生成图片
                    cmd = f"mmdc -i - -o {diagram_path}"
                    process = subprocess.Popen(
                        cmd.split(),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    stdout, stderr = process.communicate(input=mermaid_code)
                    
                    if process.returncode == 0:
                        logging.info(f"✅ 成功生成图表: {diagram_filename}")
                        # 替换mermaid代码块为图片引用
                        markdown_content = markdown_content.replace(
                            match.group(0),
                            f"\n![{diagram_filename}]({diagram_filename})\n"
                        )
                    else:
                        logging.error(f"❌ 生成图表失败: {stderr}")
                except Exception as e:
                    logging.error(f"❌ 处理图表时发生错误: {e}")
                    continue
            
            return markdown_content
        except Exception as e:
            logging.error(f"❌ 处理mermaid图表时发生错误: {e}")
            return markdown_content

    def fill_template(self, template: str, content_map: Dict[str, str], md_content_for_mermaid: str, report_filename_base: str) -> str:
        """填充LaTeX模板"""
        try:
            # 处理mermaid图表
            processed_content = self._process_all_mermaid_diagrams(md_content_for_mermaid, report_filename_base)
            
            # 转换所有内容为LaTeX格式
            for section_type, content in content_map.items():
                if content:
                    content_map[section_type] = self.convert_md_to_latex(content, section_type)
            
            # 生成参考文献部分
            bibliography = self._generate_latex_bibliography()
            
            # 填充模板
            filled_template = template.format(
                title=content_map.get('title', ''),
                abstract=content_map.get('abstract', ''),
                introduction=content_map.get('introduction', ''),
                background=content_map.get('background', ''),
                methodology=content_map.get('methodology', ''),
                timeline=content_map.get('timeline', ''),
                bibliography=bibliography
            )
            
            return filled_template
            
        except Exception as e:
            logging.error(f"❌ 填充模板时发生错误: {e}")
            raise

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
        self.send_progress_message("编译LaTeX", f"🔄 正在编译LaTeX文件: {tex_basename}")

        # 检查源文件是否存在
        if not os.path.exists(tex_full_path):
            error_msg = f"❌ 找不到源文件: {tex_full_path}"
            logging.error(error_msg)
            self.send_progress_message("错误", error_msg)
            return False

        # 复制 .cls 文件
        cls_source_file = os.path.join(self.exporter_dir, "phdproposal.cls")
        if not os.path.exists(cls_source_file):
            error_msg = f"❌ 找不到类文件: {cls_source_file}"
            logging.error(error_msg)
            self.send_progress_message("错误", error_msg)
            return False
        
        import shutil
        target_cls_file = os.path.join(output_dir, "phdproposal.cls")
        try:
            shutil.copy2(cls_source_file, target_cls_file)
            logging.info(f"✓ 已复制类文件到: {target_cls_file}")
        except Exception as e:
            error_msg = f"❌ 复制类文件失败: {e}"
            logging.error(error_msg)
            self.send_progress_message("错误", error_msg)
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
                logging.warning(f"⚠️ 复制Logo文件失败: {e}")
                # Logo是可选的，继续执行
        else:
            logging.warning(f"⚠️ 未找到Logo文件: {logo_source_file}，将不包含Logo。")

        try:
            original_cwd = os.getcwd()
            os.chdir(output_dir) # 切换到编译目录
            logging.debug(f"当前工作目录: {os.getcwd()}")
            logging.debug(f"编译文件: {tex_basename}")

            # 检查xelatex命令是否可用
            try:
                subprocess.run(['xelatex', '--version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                error_msg = "❌ 未找到xelatex命令，请确保已安装LaTeX环境\nUbuntu/Debian: sudo apt-get install texlive-full\nCentOS/RHEL: sudo yum install texlive-scheme-full"
                logging.error(error_msg)
                self.send_progress_message("错误", error_msg)
                return False

            # 第一次编译
            self.send_progress_message("编译LaTeX", "🔄 正在进行第一次编译...")
            result1 = subprocess.run([
                'xelatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                tex_basename
            ], capture_output=True, text=True, timeout=120)

            if result1.returncode != 0:
                error_msg = f"❌ 第一次xelatex编译失败:\n标准输出: {result1.stdout}\n错误输出: {result1.stderr}"
                logging.error(error_msg)
                self.send_progress_message("错误", error_msg)
                
                # 检查并输出log文件内容
                log_file = f"{tex_name_without_ext}.log"
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            log_content = f.read()
                            logging.error(f"Log文件内容:\n{log_content[-2000:]}")  # 增加输出长度
                    except Exception as e:
                        logging.error(f"读取log文件失败: {e}")
                return False

            # 第二次编译（处理交叉引用）
            self.send_progress_message("编译LaTeX", "🔄 正在进行第二次编译（处理交叉引用）...")
            result2 = subprocess.run([
                'xelatex',
                '-interaction=nonstopmode',
                '-halt-on-error',
                tex_basename
            ], capture_output=True, text=True, timeout=120)

            if result2.returncode != 0:
                error_msg = f"❌ 第二次xelatex编译失败:\n错误输出: {result2.stderr}"
                logging.error(error_msg)
                self.send_progress_message("错误", error_msg)
                return False

            pdf_filename = f"{tex_name_without_ext}.pdf"
            if os.path.exists(pdf_filename):
                success_msg = f"✅ PDF文件生成成功: {os.path.join(os.getcwd(), pdf_filename)}"
                logging.info(success_msg)
                self.send_progress_message("完成", success_msg)
                self._cleanup_temp_files(tex_name_without_ext)
                try:
                    os.remove("phdproposal.cls")
                    if os.path.exists(target_figures_dir):
                        shutil.rmtree(target_figures_dir)
                    logging.info("✓ 已清理临时类文件和Logo文件")
                except Exception as e:
                    logging.warning(f"⚠️ 清理临时文件失败: {e}")
                return True
            else:
                error_msg = "❌ PDF文件未能生成"
                logging.error(error_msg)
                self.send_progress_message("错误", error_msg)
                return False

        except subprocess.TimeoutExpired:
            error_msg = "❌ xelatex编译超时"
            logging.error(error_msg)
            self.send_progress_message("错误", error_msg)
            return False
        except Exception as e:
            error_msg = f"❌ 编译过程中发生错误: {e}"
            logging.error(error_msg)
            self.send_progress_message("错误", error_msg)
            return False
        finally:
            os.chdir(original_cwd)  # 恢复原始工作目录

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
    
    def send_progress_message(self, title: str, content: str, step: int = None, is_finish: bool = False):
        """发送进度消息到前端"""
        if step is None:
            step = self.export_step
            self.export_step += 1  # 每次发送消息后增加step值
        
        # 确保content以\n\n开头
        if not content.startswith("\n\n"):
            content = "\n\n" + content
            
        message = {
            "proposal_id": self.proposal_id,
            "step": step,
            "title": title,
            "content": content,
            "is_finish": is_finish
        }
        
        # 使用json.dumps确保消息格式正确
        print(f"QUEUE_MESSAGE:{json.dumps(message)}", flush=True)


    def export_proposal(self, output_filename: str = "generated_proposal.tex", compile_pdf: bool = True, specific_file: str = None):
        """
        主函数：导出完整的研究计划
        """
        try:
            # 重置导出步骤计数器，使用更高的初始值
            self.export_step = 100
            
            self.send_progress_message("开始导出", "🔄 开始导出研究计划...")
            logging.info("开始导出")
            
            # 读取模板
            try:
                template = self.read_template()
                logging.info("✅ 成功读取LaTeX模板")
                self.send_progress_message("读取模板", "📄 读取LaTeX模板...")
            except FileNotFoundError as e:
                logging.error(f"❌ 未找到LaTeX模板文件: {e}")
                self.send_progress_message("错误", f"❌ 未找到LaTeX模板文件: {e}")
                raise
            except Exception as e:
                logging.error(f"❌ 读取LaTeX模板时发生错误: {e}")
                self.send_progress_message("错误", f"❌ 读取LaTeX模板时发生错误: {e}")
                raise
            
            # 读取Markdown文件
            try:
                md_files = self.read_markdown_files(specific_file)
                logging.info("✅ 成功读取Markdown文件")
                logging.info(f"文件为: {list(md_files.keys())}")
                self.send_progress_message("读取文件", "📚 读取Markdown文件...")
            except FileNotFoundError as e:
                logging.error(f"❌ 未找到Markdown文件: {e}")
                self.send_progress_message("错误", f"❌ 未找到Markdown文件: {e}")
                raise
            except Exception as e:
                logging.error(f"❌ 读取Markdown文件时发生错误: {e}")
                self.send_progress_message("错误", f"❌ 读取Markdown文件时发生错误: {e}")
                raise
            
            # 提取内容
            try:
                content_map = self.extract_content_by_type(md_files)
                logging.info("✅ 成功提取各部分内容")
                self.send_progress_message("提取内容", "🔍 提取各部分内容...")
            except Exception as e:
                logging.error(f"❌ 提取内容时发生错误: {e}")
                self.send_progress_message("错误", f"❌ 提取内容时发生错误: {e}")
                raise
            
            # 加载参考文献
            try:
                md_filepath = list(md_files.keys())[0]  # 使用第一个Markdown文件
                self._load_references_json(md_filepath)
                if self.references_data:
                    logging.info("✅ 成功加载参考文献")
                    self.send_progress_message("加载参考文献", "📚 加载参考文献...")
                else:
                    logging.warning("⚠️ 未找到参考文献数据")
                    self.send_progress_message("警告", "⚠️ 未找到参考文献数据")
            except Exception as e:
                logging.error(f"❌ 加载参考文献时发生错误: {e}")
                self.send_progress_message("错误", f"❌ 加载参考文献时发生错误: {e}")
                raise
            
            # 生成报告文件名
            if specific_file:
                report_filename_base = os.path.splitext(os.path.basename(specific_file))[0]
            else:
                report_filename_base = os.path.splitext(os.path.basename(list(md_files.keys())[0]))[0]
            
            # 填充模板
            try:
                filled_template = self.fill_template(template, content_map, list(md_files.values())[0], report_filename_base)
                logging.info("✅ 成功填充模板")
                self.send_progress_message("填充模板", "📝 填充LaTeX模板...")
            except Exception as e:
                logging.error(f"❌ 填充模板时发生错误: {e}")
                self.send_progress_message("错误", f"❌ 填充模板时发生错误: {e}")
                raise
            
            # 保存LaTeX文件
            try:
                tex_filename = f"{report_filename_base}.tex"
                tex_path = os.path.join(self.output_dir, tex_filename)
                with open(tex_path, 'w', encoding='utf-8') as f:
                    f.write(filled_template)
                logging.info(f"✅ 成功保存LaTeX文件: {tex_path}")
                self.send_progress_message("保存文件", "💾 保存LaTeX文件...")
            except Exception as e:
                logging.error(f"❌ 保存LaTeX文件时发生错误: {e}")
                self.send_progress_message("错误", f"❌ 保存LaTeX文件时发生错误: {e}")
                raise
            
            # 编译PDF
            if compile_pdf:
                try:
                    if self.compile_with_xelatex(tex_filename):
                        pdf_filename = f"{report_filename_base}.pdf"
                        logging.info(f"✅ 成功生成PDF文件: {pdf_filename}")
                        self.send_progress_message("完成", f"✅ 成功生成PDF文件: {pdf_filename}")
                    else:
                        error_msg = "❌ PDF编译失败"
                        logging.error(error_msg)
                        self.send_progress_message("错误", error_msg)
                        raise Exception(error_msg)
                except Exception as e:
                    logging.error(f"❌ 编译PDF时发生错误: {e}")
                    self.send_progress_message("错误", f"❌ 编译PDF时发生错误: {e}")
                    raise
            
            return True
            
        except Exception as e:
            logging.error(f"❌ 导出过程中发生错误: {e}")
            self.send_progress_message("错误", f"❌ 导出过程中发生错误: {e}")
            raise

    def _read_file(self, filepath: str) -> str:
        """读取文件内容"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            logging.error(f"❌ 读取文件失败 {filepath}: {str(e)}")
            raise

def main():
    # 设置环境变量以防止自动打开文件
    os.environ.update({
        'EDITOR': 'none',
        'VISUAL': 'none',
        'LATEX_EDITOR': 'none',
        'TEXEDIT': 'none',
        'TEX_EDITOR': 'none',
        'PYTHONUNBUFFERED': '1'
    })
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='导出提案为LaTeX和PDF格式')
    parser.add_argument('markdown_file', nargs='?', help='要导出的Markdown文件路径（可选，默认使用最新的md文件）')
    parser.add_argument('proposal_id', nargs='?', default='none', help='提案ID（可选，默认为none）')
    args = parser.parse_args()
    
    try:
        # 创建导出器实例
        exporter = ProposalExporter(proposal_id=args.proposal_id)
        
        # 如果没有指定markdown文件，则使用最新的md文件
        if not args.markdown_file:
            md_files = exporter.read_markdown_files()
            if not md_files:
                raise FileNotFoundError("未找到任何Markdown文件")
            # 获取最新的md文件
            latest_md = max(md_files.keys(), key=lambda x: os.path.getmtime(x))
            args.markdown_file = latest_md
            logging.info(f"使用最新的Markdown文件: {args.markdown_file}")
        else:
            # 如果指定了文件，确保使用完整路径
            if not os.path.isabs(args.markdown_file):
                args.markdown_file = os.path.join(exporter.markdown_source_dir, args.markdown_file)
            logging.info(f"使用指定的Markdown文件: {args.markdown_file}")
        
        # 验证文件是否存在
        if not os.path.exists(args.markdown_file):
            raise FileNotFoundError(f"找不到指定的Markdown文件: {args.markdown_file}")
        
        logging.info(f"提案ID: {args.proposal_id}")
        
        # 生成时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 从文件名中提取研究领域
        research_field = os.path.basename(args.markdown_file).split('_')[0]
        
        # 构建输出文件名
        output_filename = f"{args.proposal_id}_{timestamp}.tex"
        
        # 导出提案
        success = exporter.export_proposal(
            output_filename=output_filename,
            compile_pdf=True,
            specific_file=args.markdown_file
        )
        
        if success:
            logging.info("\n导出完成！")
            logging.info(f"LaTeX文件: {os.path.join(exporter.output_dir, output_filename)}")
            logging.info("✅ 所有文件已成功生成！")
        else:
            logging.error("❌ 导出失败！")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"❌ 导出过程中发生错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main()
