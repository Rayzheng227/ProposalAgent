"""
将最终的md转化为一个格式美观的pdf
"""
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PDFExporter:
    def __init__(self):
        self.output_dir = Path("./output")
        self.temp_dir = Path("./temp")
        self.temp_dir.mkdir(exist_ok=True)
        
    def check_dependencies(self):
        """检查必要的依赖"""
        dependencies = ['pandoc', 'xelatex']
        missing = []
        
        for dep in dependencies:
            try:
                subprocess.run([dep, '--version'], capture_output=True, check=True)
                logging.info(f"✅ {dep} 已安装")
            except (subprocess.CalledProcessError, FileNotFoundError):
                missing.append(dep)
                logging.error(f"❌ {dep} 未找到")
        
        if missing:
            logging.error(f"请安装缺失的依赖: {', '.join(missing)}")
            return False
        return True
    
    def create_yaml_header(self, research_field: str) -> str:
        """创建YAML元数据头"""
        yaml_header = f"""---
title: "研究计划书：{research_field}"
author: "ProposalAgent"
date: "{datetime.now().strftime('%Y年%m月%d日')}"
documentclass: article
geometry:
- margin=2.5cm
- a4paper
fontsize: 12pt
CJKmainfont: "Noto Sans CJK SC"
CJKsansfont: "Noto Sans CJK SC"
CJKmonofont: "Noto Sans Mono CJK SC"
mainfont: "Liberation Serif"
sansfont: "Liberation Sans"
monofont: "Liberation Mono"
linestretch: 1.5
indent: true
toc: true
toc-depth: 3
number-sections: true
colorlinks: true
linkcolor: blue
urlcolor: blue
citecolor: blue
header-includes:
- \\usepackage{{xeCJK}}
- \\usepackage{{setspace}}
- \\usepackage{{indentfirst}}
- \\usepackage{{titlesec}}
- \\usepackage{{fancyhdr}}
- \\usepackage{{lastpage}}
- \\usepackage{{booktabs}}
- \\usepackage{{longtable}}
- \\usepackage{{array}}
- \\usepackage{{multirow}}
- \\usepackage{{wrapfig}}
- \\usepackage{{float}}
- \\usepackage{{colortbl}}
- \\usepackage{{pdflscape}}
- \\usepackage{{tabu}}
- \\usepackage{{threeparttable}}
- \\usepackage{{threeparttablex}}
- \\usepackage{{ulem}}
- \\usepackage{{makecell}}
- \\pagestyle{{fancy}}
- \\fancyhf{{}}
- \\fancyhead[L]{{研究计划书：{research_field}}}
- \\fancyhead[R]{{\\thepage/\\pageref{{LastPage}}}}
- \\fancyfoot[C]{{\\thepage}}
- \\renewcommand{{\\headrulewidth}}{{0.4pt}}
- \\renewcommand{{\\footrulewidth}}{{0.4pt}}
- \\setlength{{\\parindent}}{{2em}}
---

"""
        return yaml_header
    
    def preprocess_markdown(self, content: str, research_field: str) -> str:
        """预处理Markdown内容"""
        # 添加YAML头
        yaml_header = self.create_yaml_header(research_field)
        
        # 移除可能存在的YAML头（避免重复）
        if content.startswith('---'):
            # 找到第二个 ---
            end_yaml = content.find('---', 3)
            if end_yaml != -1:
                content = content[end_yaml + 3:].strip()
        
        # 修复可能的YAML解析问题
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            # 移除可能导致YAML解析错误的行
            if line.strip().startswith('```') and 'yaml' in line.lower():
                continue
            if line.strip() == '---' and len(processed_lines) > 10:
                # 如果在内容中间遇到 ---，替换为分隔线
                processed_lines.append('\n---\n')
                continue
            processed_lines.append(line)
        
        # 合并内容
        full_content = yaml_header + '\n'.join(processed_lines)
        
        # 确保参考文献格式正确
        full_content = self.fix_references(full_content)
        
        return full_content
    
    def fix_references(self, content: str) -> str:
        """修复参考文献格式"""
        import re
        
        # 修复可能的引用格式问题
        # 将 [数字] 格式的引用保持不变
        # 但确保它们不会被Pandoc误解析
        
        lines = content.split('\n')
        processed_lines = []
        in_references = False
        
        for line in lines:
            if '## 参考文献' in line or '# 参考文献' in line:
                in_references = True
                processed_lines.append(line)
                continue
            
            if in_references and line.strip().startswith('[') and ']' in line:
                # 这是参考文献条目，确保格式正确
                line = line.strip()
                processed_lines.append(line)
            else:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def create_bibliography_file(self, content: str) -> str:
        """创建BibTeX文件（可选）"""
        bib_path = self.temp_dir / "refs.bib"
        
        # 这里可以从内容中提取参考文献并转换为BibTeX格式
        # 为简单起见，创建一个空的bib文件
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write("% 参考文献文件\n")
        
        return str(bib_path)
    
    def get_latest_markdown_file(self) -> Path:
        """获取最新的Markdown文件"""
        if not self.output_dir.exists():
            raise FileNotFoundError("输出目录不存在")
        
        md_files = list(self.output_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError("未找到Markdown文件")
        
        # 按修改时间排序，返回最新的
        latest_file = max(md_files, key=lambda x: x.stat().st_mtime)
        return latest_file
    
    def convert_to_pdf(self, md_file: Path, output_pdf: Path = None) -> Path:
        """将Markdown转换为PDF"""
        if not self.check_dependencies():
            raise RuntimeError("缺少必要的依赖")
        
        # 读取Markdown内容
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 从文件名提取研究领域
        research_field = "研究主题"
        if "Research_Proposal_" in md_file.name:
            parts = md_file.name.split("_")
            if len(parts) >= 3:
                research_field = parts[2]
        
        # 预处理内容
        processed_content = self.preprocess_markdown(content, research_field)
        
        # 创建临时处理后的Markdown文件
        temp_md = self.temp_dir / f"processed_{md_file.name}"
        with open(temp_md, 'w', encoding='utf-8') as f:
            f.write(processed_content)
        
        # 确定输出PDF文件名
        if output_pdf is None:
            pdf_name = md_file.stem + ".pdf"
            output_pdf = self.output_dir / pdf_name
        
        # 创建BibTeX文件
        bib_file = self.create_bibliography_file(content)
        
        # Pandoc命令
        pandoc_cmd = [
            'pandoc',
            str(temp_md),
            '--pdf-engine=xelatex',
            '--standalone',
            '--toc',
            '--number-sections',
            '--highlight-style=tango',
            '-V', 'geometry:margin=2.5cm',
            '-V', 'fontsize=12pt',
            '-V', 'linestretch=1.5',
            '-V', 'indent=true',
            # '--filter=pandoc-crossref',  # 如果安装了crossref过滤器
            '-o', str(output_pdf)
        ]
        
        logging.info(f"🔄 开始转换: {md_file.name} -> {output_pdf.name}")
        logging.info(f"执行命令: {' '.join(pandoc_cmd)}")
        
        try:
            result = subprocess.run(
                pandoc_cmd,
                capture_output=True,
                text=True,
                cwd=self.temp_dir.parent,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                logging.info(f"✅ PDF生成成功: {output_pdf}")
                # 清理临时文件
                temp_md.unlink()
                return output_pdf
            else:
                logging.error(f"❌ Pandoc执行失败:")
                logging.error(f"stderr: {result.stderr}")
                logging.error(f"stdout: {result.stdout}")
                raise RuntimeError(f"Pandoc转换失败: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logging.error("❌ PDF转换超时")
            raise RuntimeError("PDF转换超时")
        except Exception as e:
            logging.error(f"❌ PDF转换出错: {e}")
            raise
    
    def export_latest(self) -> Path:
        """导出最新的Markdown文件为PDF"""
        try:
            latest_md = self.get_latest_markdown_file()
            logging.info(f"📄 找到最新文件: {latest_md.name}")
            
            pdf_path = self.convert_to_pdf(latest_md)
            return pdf_path
            
        except Exception as e:
            logging.error(f"❌ 导出失败: {e}")
            raise
    
    def export_specific_file(self, md_file_path: str) -> Path:
        """导出指定的Markdown文件为PDF"""
        md_path = Path(md_file_path)
        if not md_path.exists():
            raise FileNotFoundError(f"文件不存在: {md_file_path}")
        
        pdf_path = self.convert_to_pdf(md_path)
        return pdf_path


def install_fonts_linux():
    """在Linux上安装中文字体的辅助函数"""
    print("🔧 检测到字体问题，以下是在Linux上安装中文字体的建议：")
    print("\n1. 安装基本中文字体包:")
    print("   sudo apt-get update")
    print("   sudo apt-get install fonts-wqy-microhei fonts-wqy-zenhei")
    print("   sudo apt-get install fonts-noto-cjk fonts-noto-cjk-extra")
    print("   sudo apt-get install xfonts-wqy")
    
    print("\n2. 安装Windows字体 (可选):")
    print("   sudo apt-get install ttf-mscorefonts-installer")
    
    print("\n3. 更新字体缓存:")
    print("   sudo fc-cache -f -v")
    
    print("\n4. 检查可用字体:")
    print("   fc-list :lang=zh-cn")


if __name__ == "__main__":
    exporter = PDFExporter()
    
    try:
        # 导出最新的Markdown文件
        pdf_path = exporter.export_latest()
        print(f"✅ PDF导出成功: {pdf_path}")
        
        # 打开PDF文件 (Linux)
        try:
            subprocess.run(['xdg-open', str(pdf_path)], check=True)
        except:
            print(f"请手动打开PDF文件: {pdf_path}")
            
    except FileNotFoundError as e:
        print(f"❌ 文件未找到: {e}")
        print("请先运行agent.py生成研究计划书")
    except RuntimeError as e:
        if "font" in str(e).lower() or "字体" in str(e):
            print(f"❌ 字体相关错误: {e}")
            install_fonts_linux()
        else:
            print(f"❌ 运行时错误: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")