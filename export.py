from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import os
import logging
from datetime import datetime
from typing import Dict, Any, List

class ProposalExporter:
    """研究计划书导出工具类"""
    
    def __init__(self, output_dir: str = "output"):
        self.logger = logging.getLogger(__name__)
        self.output_dir = output_dir
        self.font_dir = os.path.join(output_dir, "fonts")
        self.chinese_font_available = False
        self._ensure_output_dir()
        self._ensure_font_dir()
        self._register_fonts()
        self._setup_styles()

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            self.logger.info(f"创建输出目录: {self.output_dir}")
    
    def _ensure_font_dir(self):
        """确保字体目录存在"""
        if not os.path.exists(self.font_dir):
            os.makedirs(self.font_dir)
            self.logger.info(f"创建字体目录: {self.font_dir}")
    
    def _register_fonts(self) -> bool:
        """注册中文字体"""
        try:
            # 首先检查字体目录中是否已有字体文件
            local_font_path = os.path.join(self.font_dir, "NotoSansCJK-Regular.ttc")
            if os.path.exists(local_font_path):
                try:
                    pdfmetrics.registerFont(TTFont('ChineseFont', local_font_path))
                    self.logger.info(f"成功注册本地中文字体: {local_font_path}")
                    self.chinese_font_available = True
                    return True
                except Exception as e:
                    self.logger.warning(f"本地字体注册失败: {e}")
            
            # 尝试注册系统中文字体
            font_paths = [
                # macOS
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
                "/Library/Fonts/Arial Unicode MS.ttf",
                # Linux - 更多中文字体路径
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                # Windows
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/simkai.ttf",
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                        self.logger.info(f"成功注册系统中文字体: {font_path}")
                        self.chinese_font_available = True
                        return True
                    except Exception as e:
                        self.logger.warning(f"字体注册失败 {font_path}: {e}")
                        continue
            
            # 如果没有找到字体文件，尝试下载并使用免费字体
            self.logger.warning("未找到系统中文字体，尝试下载字体")
            success = self._try_download_font()
            self.chinese_font_available = success
            return success
                
        except Exception as e:
            self.logger.error(f"字体注册过程出错: {e}")
            self.chinese_font_available = False
            return False
    
    def _try_download_font(self) -> bool:
        """尝试下载免费中文字体"""
        try:
            import urllib.request
            import ssl
            
            # 创建SSL上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # 使用更可靠的字体源 - 直接从可访问的CDN下载
            font_configs = [
                {
                    "url": "https://fonts.gstatic.com/s/notosanstc/v35/nKKF-GM_FYFRJvXzVXaAPe97MBmnOSsb.ttf",
                    "filename": "NotoSansTC-Regular.ttf",
                    "name": "思源黑体TC"
                },
                {
                    "url": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansSC/NotoSansSC-Regular.ttf",
                    "filename": "NotoSansSC-Regular.ttf",
                    "name": "思源黑体SC"
                }
            ]
            
            for font_config in font_configs:
                font_path = os.path.join(self.font_dir, font_config["filename"])
                
                try:
                    if not os.path.exists(font_path):
                        self.logger.info(f"正在下载中文字体: {font_config['name']}")
                        
                        # 使用更简单的下载方式
                        request = urllib.request.Request(
                            font_config["url"],
                            headers={
                                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                                'Accept': '*/*'
                            }
                        )
                        
                        with urllib.request.urlopen(request, context=ssl_context, timeout=60) as response:
                            font_data = response.read()
                            
                        with open(font_path, 'wb') as f:
                            f.write(font_data)
                        
                        self.logger.info(f"字体下载完成: {font_path} ({len(font_data)} bytes)")
                    
                    # 验证字体文件大小
                    file_size = os.path.getsize(font_path)
                    if file_size < 50000:  # 至少50KB
                        self.logger.warning(f"字体文件太小，可能损坏: {font_path} ({file_size} bytes)")
                        os.remove(font_path)
                        continue
                    
                    # 注册字体
                    pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                    self.logger.info(f"中文字体注册成功: {font_config['name']} ({file_size} bytes)")
                    
                    # 测试字体是否真的可用
                    if self._test_chinese_font():
                        return True
                    else:
                        self.logger.warning("字体注册成功但测试失败")
                        continue
                    
                except Exception as e:
                    self.logger.warning(f"字体处理失败 {font_config['name']}: {e}")
                    if os.path.exists(font_path):
                        try:
                            os.remove(font_path)
                        except:
                            pass
                    continue
            
            # 最后尝试创建一个简单的字体文件（备用方案）
            return self._create_fallback_font()
            
        except Exception as e:
            self.logger.error(f"字体下载过程出错: {e}")
            return False

    def _test_chinese_font(self) -> bool:
        """测试中文字体是否可用"""
        try:
            from reportlab.platypus import SimpleDocTemplate
            from reportlab.lib.pagesizes import A4
            import tempfile
            
            # 创建临时测试文件
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=True) as tmp_file:
                doc = SimpleDocTemplate(tmp_file.name, pagesize=A4)
                story = []
                
                # 使用中文字体创建测试段落
                test_style = ParagraphStyle(
                    'TestStyle',
                    fontName='ChineseFont',
                    fontSize=12
                )
                
                story.append(Paragraph("测试中文字体", test_style))
                doc.build(story)
                
                # 检查文件是否成功生成
                return os.path.getsize(tmp_file.name) > 1000
                
        except Exception as e:
            self.logger.warning(f"字体测试失败: {e}")
            return False

    def _create_fallback_font(self) -> bool:
        """创建备用字体解决方案"""
        try:
            self.logger.info("尝试创建备用字体解决方案")
            
            # 使用内置的Symbol字体作为中文字体的替代
            # 虽然不完美，但至少不会显示方块
            pdfmetrics.registerFont(TTFont('ChineseFont', 'Helvetica'))
            
            # 修改文本转换策略，确保所有中文都被转换
            self.force_text_conversion = True
            
            self.logger.info("备用字体方案已启用")
            return False  # 返回False表示需要文本转换
            
        except Exception as e:
            self.logger.error(f"备用字体方案失败: {e}")
            return False

    def _get_font_name(self, bold: bool = False) -> str:
        """获取可用的字体名称"""
        if self.chinese_font_available:
            return 'ChineseFont'
        else:
            return 'Helvetica-Bold' if bold else 'Helvetica'

    def _setup_styles(self):
        """设置PDF样式"""
        self.styles = getSampleStyleSheet()
        
        # 标题样式
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=20,
            spaceAfter=30,
            spaceBefore=20,
            alignment=TA_CENTER,
            textColor=colors.darkblue,
            fontName=self._get_font_name()
        )
        
        # 一级标题样式
        self.heading1_style = ParagraphStyle(
            'CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue,
            fontName=self._get_font_name()
        )
        
        # 二级标题样式
        self.heading2_style = ParagraphStyle(
            'CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15,
            textColor=colors.darkslategray,
            fontName=self._get_font_name()
        )
        
        # 正文样式
        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            leading=16,
            alignment=TA_JUSTIFY,
            fontName=self._get_font_name()
        )
        
        # 小字体样式
        self.small_style = ParagraphStyle(
            'CustomSmall',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=4,
            leading=12,
            textColor=colors.gray,
            fontName=self._get_font_name()
        )
        
        # 引用样式
        self.citation_style = ParagraphStyle(
            'CustomCitation',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            leading=14,
            leftIndent=20,
            rightIndent=20,
            fontName=self._get_font_name()
        )

    def _safe_paragraph(self, text: str, style) -> Paragraph:
        """安全创建段落，处理特殊字符和中文显示"""
        if not text:
            return Paragraph("", style)
        
        # 强制转换中文或字体不可用时转换
        if not self.chinese_font_available or getattr(self, 'force_text_conversion', False):
            text = self._fallback_text_conversion(text)
        
        # 清理文本，移除可能导致问题的字符
        clean_text = text.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        
        # 处理换行
        clean_text = clean_text.replace('\n', '<br/>')
        
        return Paragraph(clean_text, style)

    def _fallback_text_conversion(self, text: str) -> str:
        """中文字体不可用时的文本转换"""
        import re
        
        # 扩展的中文到英文映射
        replacements = {
            '研究计划书': 'Research Proposal',
            '研究主题': 'Research Topic',
            '生成时间': 'Generated Time',
            '收集论文': 'Collected papers',
            '网络资源': 'Web Resources',
            '执行步骤': 'Execution Steps',
            '目录': 'Table of Contents',
            '研究计划概览': 'Research Plan Overview',
            '引言': 'Introduction',
            '文献综述': 'Literature Review',
            '研究设计': 'Research Design',
            '时间计划': 'Timeline',
            '预期结果': 'Expected Results',
            '附录': 'Appendix',
            '执行记录': 'Execution Log',
            '文献统计': 'Literature Statistics',
            '文献检索执行记录': 'Literature Search Execution Log',
            '总计执行步骤': 'Total Execution Steps',
            '步骤': 'Step',
            '描述': 'Description',
            '状态': 'Status',
            '成功': 'Success',
            '失败': 'Failed',
            '未知步骤': 'Unknown Step',
            '暂无执行记录': 'No execution records',
            '文献收集统计': 'Literature Collection Statistics',
            '文献类型': 'Literature Type',
            '数量': 'Count',
            '说明': 'Description',
            '学术论文': 'Academic papers',
            '最新资讯': 'Latest Information',
            '收集到的ArXiv论文': 'Collected ArXiv papers',
            '作者': 'Authors',
            '发表时间': 'Published Date',
            '人工智能': 'Artificial Intelligence',
            '医疗领域': 'Medical Field',
            '应用': 'Application',
            '探索': 'Explore',
            '医疗诊断': 'Medical Diagnosis',
            '分析': 'Analysis',
            '现有技术': 'Existing Technology',
            '局限性': 'Limitations',
            '本研究': 'This Research',
            '旨在': 'Aims to',
            '探讨': 'Discuss',
            '技术': 'Technology',
            '创新': 'Innovation',
            '参考文献': 'References',
            '年': '/',
            '月': '/',
            '日': '',
            '篇': ' papers',
            '条': ' items',
            '个': ' items',
            '待完善': 'To be completed'
        }
        
        result = text
        
        # 先进行精确匹配替换
        for chinese, english in replacements.items():
            result = result.replace(chinese, english)
        
        # 处理剩余的中文字符（用拼音或[Chinese Text]标记）
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
        chinese_matches = chinese_pattern.findall(result)
        
        for match in chinese_matches:
            if len(match) <= 4:  # 短的中文词用[CN]标记
                result = result.replace(match, f'[CN:{match}]')
            else:  # 长的中文段落用[Chinese Text]标记
                result = result.replace(match, '[Chinese Text]')
        
        return result

    def _create_cover_page(self, result: Dict[str, Any]) -> List:
        """创建封面页"""
        cover_elements = []
        
        # 添加一些空白
        cover_elements.append(Spacer(1, 2*inch))
        
        # 主标题
        title = f"研究计划书"
        cover_elements.append(self._safe_paragraph(title, self.title_style))
        cover_elements.append(Spacer(1, 0.5*inch))
        
        # 研究主题
        subtitle = f"研究主题：{result['research_field']}"
        cover_elements.append(self._safe_paragraph(subtitle, self.heading1_style))
        cover_elements.append(Spacer(1, 1*inch))
        
        # 生成信息
        gen_time = datetime.now().strftime("%Y年%m月%d日")
        info_data = [
            ['生成时间：', gen_time],
            ['收集论文：', f"{len(result.get('arxiv_papers', []))} 篇"],
            ['网络资源：', f"{len(result.get('web_search_results', []))} 条"],
            ['执行步骤：', f"{len(result.get('execution_memory', []))} 个"]
        ]
        
        info_table = Table(info_data, colWidths=[2*inch, 3*inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self._get_font_name()),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.lightgrey),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        cover_elements.append(info_table)
        cover_elements.append(PageBreak())
        
        return cover_elements

    def _create_toc(self, result: Dict[str, Any]) -> List:
        """创建目录"""
        toc_elements = []
        
        toc_elements.append(self._safe_paragraph("目录", self.heading1_style))
        toc_elements.append(Spacer(1, 20))
        
        toc_data = [
            ['1. 研究计划概览', '3'],
            ['2. 引言', '4'],
            ['3. 文献综述', '待完善'],
            ['4. 研究设计', '待完善'],
            ['5. 时间计划', '待完善'],
            ['6. 预期结果', '待完善'],
            ['附录A: 执行记录', f"{5 + (1 if result.get('introduction') else 0)}"],
            ['附录B: 文献统计', f"{6 + (1 if result.get('introduction') else 0)}"],
        ]
        
        toc_table = Table(toc_data, colWidths=[4*inch, 1*inch])
        toc_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self._get_font_name()),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        toc_elements.append(toc_table)
        toc_elements.append(PageBreak())
        
        return toc_elements

    def _create_research_plan_section(self, result: Dict[str, Any]) -> List:
        """创建研究计划概览部分"""
        elements = []
        
        elements.append(self._safe_paragraph("1. 研究计划概览", self.heading1_style))
        elements.append(Spacer(1, 12))
        
        if result.get("research_plan"):
            # 将研究计划按段落分割
            plan_text = result["research_plan"]
            paragraphs = plan_text.split('\n\n')
            
            for para in paragraphs:
                if para.strip():
                    # 检查是否是标题（通常以数字或特殊符号开头）
                    if para.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '**', '#')):
                        elements.append(self._safe_paragraph(para.strip(), self.heading2_style))
                    else:
                        elements.append(self._safe_paragraph(para.strip(), self.normal_style))
                    elements.append(Spacer(1, 6))
        else:
            elements.append(self._safe_paragraph("研究计划尚未生成。", self.normal_style))
        
        elements.append(PageBreak())
        return elements

    def _create_introduction_section(self, result: Dict[str, Any]) -> List:
        """创建引言部分"""
        elements = []
        
        elements.append(self._safe_paragraph("2. 引言", self.heading1_style))
        elements.append(Spacer(1, 12))
        
        if result.get("introduction"):
            intro_text = result["introduction"]
            
            # 处理参考文献部分
            if "## 参考文献" in intro_text:
                main_text, ref_text = intro_text.split("## 参考文献", 1)
            else:
                main_text = intro_text
                ref_text = ""
            
            # 处理主要内容
            paragraphs = main_text.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    elements.append(self._safe_paragraph(para.strip(), self.normal_style))
                    elements.append(Spacer(1, 8))
            
            # 处理参考文献
            if ref_text:
                elements.append(Spacer(1, 20))
                elements.append(self._safe_paragraph("参考文献", self.heading2_style))
                elements.append(Spacer(1, 10))
                
                ref_lines = ref_text.strip().split('\n')
                for line in ref_lines:
                    if line.strip():
                        elements.append(self._safe_paragraph(line.strip(), self.citation_style))
                        elements.append(Spacer(1, 4))
        else:
            elements.append(self._safe_paragraph("引言部分尚未生成。", self.normal_style))
        
        elements.append(PageBreak())
        return elements

    def _create_appendix_section(self, result: Dict[str, Any]) -> List:
        """创建附录部分"""
        elements = []
        
        # 附录A: 执行记录
        elements.append(self._safe_paragraph("附录A: 文献检索执行记录", self.heading1_style))
        elements.append(Spacer(1, 12))
        
        execution_memory = result.get("execution_memory", [])
        if execution_memory:
            elements.append(self._safe_paragraph(f"总计执行步骤：{len(execution_memory)} 个", self.normal_style))
            elements.append(Spacer(1, 10))
            
            # 创建执行记录表格
            exec_data = [['步骤', '描述', '状态']]
            for i, memory in enumerate(execution_memory, 1):
                status = "✓ 成功" if memory.get('success', False) else "✗ 失败"
                desc = memory.get('description', '未知步骤')
                # 限制描述长度
                if len(desc) > 50:
                    desc = desc[:47] + "..."
                exec_data.append([str(i), desc, status])
            
            exec_table = Table(exec_data, colWidths=[0.8*inch, 3.5*inch, 1*inch])
            exec_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), self._get_font_name()),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('FONTSIZE', (0, 0), (-1, 0), 10),  # 表头稍大
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # 描述列左对齐
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            elements.append(exec_table)
        else:
            elements.append(self._safe_paragraph("暂无执行记录。", self.normal_style))
        
        elements.append(Spacer(1, 30))
        
        # 附录B: 文献统计
        elements.append(self._safe_paragraph("附录B: 文献收集统计", self.heading1_style))
        elements.append(Spacer(1, 12))
        
        arxiv_papers = result.get("arxiv_papers", [])
        web_results = result.get("web_search_results", [])
        
        stats_data = [
            ['文献类型', '数量', '说明'],
            ['ArXiv论文', f"{len(arxiv_papers)} 篇", '学术论文'],
            ['网络资源', f"{len(web_results)} 条", '最新资讯']
        ]
        
        stats_table = Table(stats_data, colWidths=[1.5*inch, 1*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self._get_font_name()),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        elements.append(stats_table)
        
        # 论文详细列表（前10篇）
        if arxiv_papers:
            elements.append(Spacer(1, 20))
            elements.append(self._safe_paragraph("收集到的ArXiv论文（前10篇）", self.heading2_style))
            elements.append(Spacer(1, 10))
            
            for i, paper in enumerate(arxiv_papers[:10], 1):
                if "error" not in paper:
                    title = paper.get('title', 'Unknown')
                    authors = ', '.join(paper.get('authors', []))
                    published = paper.get('published', 'Unknown')
                    
                    elements.append(self._safe_paragraph(f"{i}. {title}", self.normal_style))
                    elements.append(self._safe_paragraph(f"作者：{authors}", self.small_style))
                    elements.append(self._safe_paragraph(f"发表时间：{published}", self.small_style))
                    elements.append(Spacer(1, 8))
        
        return elements

    def generate_pdf_report(self, result: Dict[str, Any], filename: str = None) -> str:
        """生成PDF格式的研究计划书"""
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"research_proposal_{timestamp}.pdf"
            
            # 确保输出到output目录
            if not os.path.isabs(filename):
                filename = os.path.join(self.output_dir, filename)
            
            self.logger.info(f"开始生成PDF报告: {filename}")
            self.logger.info(f"中文字体可用状态: {self.chinese_font_available}")
            
            # 创建PDF文档
            doc = SimpleDocTemplate(
                filename, 
                pagesize=A4,
                rightMargin=72, 
                leftMargin=72,
                topMargin=72, 
                bottomMargin=72
            )
            
            # 构建文档内容
            story = []
            
            # 添加各个部分
            story.extend(self._create_cover_page(result))
            story.extend(self._create_toc(result))
            story.extend(self._create_research_plan_section(result))
            story.extend(self._create_introduction_section(result))
            story.extend(self._create_appendix_section(result))
            
            # 生成PDF
            doc.build(story)
            
            self.logger.info(f"✅ PDF报告已生成：{filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"PDF生成失败: {e}")
            raise e

    def generate_simple_pdf(self, result: Dict[str, Any], filename: str = None) -> str:
        """生成简化版PDF（用于字体问题时的备选方案）"""
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"research_proposal_simple_{timestamp}.pdf"
            
            # 确保输出到output目录
            if not os.path.isabs(filename):
                filename = os.path.join(self.output_dir, filename)
            
            # 使用基础样式
            styles = getSampleStyleSheet()
            
            doc = SimpleDocTemplate(filename, pagesize=A4)
            story = []
            
            # 标题
            title = f"Research Proposal: {result['research_field']}"
            story.append(Paragraph(title, styles['Title']))
            story.append(Spacer(1, 20))
            
            # 基本信息
            gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            story.append(Paragraph(f"Generated: {gen_time}", styles['Normal']))
            story.append(Spacer(1, 20))
            
            # 研究计划
            if result.get("research_plan"):
                story.append(Paragraph("Research Plan", styles['Heading1']))
                story.append(Spacer(1, 12))
                
                # 简单处理文本
                plan_text = result["research_plan"].replace('\n', '<br/>')
                story.append(Paragraph(plan_text, styles['Normal']))
                story.append(Spacer(1, 20))
            
            # 引言
            if result.get("introduction"):
                story.append(Paragraph("Introduction", styles['Heading1']))
                story.append(Spacer(1, 12))
                
                intro_text = result["introduction"].replace('\n', '<br/>')
                story.append(Paragraph(intro_text, styles['Normal']))
                story.append(Spacer(1, 20))
            
            # 统计信息
            story.append(Paragraph("Statistics", styles['Heading1']))
            story.append(Spacer(1, 12))
            
            stats_text = f"""
            Execution Steps: {len(result.get('execution_memory', []))}<br/>
            ArXiv papers: {len(result.get('arxiv_papers', []))}<br/>
            Web Results: {len(result.get('web_search_results', []))}
            """
            story.append(Paragraph(stats_text, styles['Normal']))
            
            doc.build(story)
            self.logger.info(f"✅ 简化版PDF已生成：{filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"简化版PDF生成失败: {e}")
            raise e


# 便捷函数
def export_to_pdf(result: Dict[str, Any], filename: str = None, simple: bool = False) -> str:
    """
    导出研究计划书为PDF格式
    
    Args:
        result: 研究计划书数据
        filename: 输出文件名（可选）
        simple: 是否使用简化版（适用于字体问题时）
    
    Returns:
        生成的PDF文件路径
    """
    exporter = ProposalExporter()
    
    if simple:
        return exporter.generate_simple_pdf(result, filename)
    else:
        try:
            return exporter.generate_pdf_report(result, filename)
        except Exception as e:
            logging.warning(f"标准PDF生成失败，尝试简化版: {e}")
            return exporter.generate_simple_pdf(result, filename)


if __name__ == "__main__":
    # 设置日志级别以便看到详细信息
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 测试代码
    test_result = {
        "research_field": "人工智能在医疗领域的应用",
        "research_plan": "这是一个测试研究计划...\n\n## 研究目标\n1. 探索AI在医疗诊断中的应用\n2. 分析现有技术的局限性",
        "introduction": "这是引言部分的测试内容...\n\n本研究旨在探讨人工智能技术在医疗领域的创新应用。\n\n## 参考文献\n[1] Smith, J. (2023). AI in Healthcare. Nature Medicine.\n[2] Zhang, L. (2023). Deep Learning for Medical Diagnosis.",
        "execution_memory": [
            {"description": "搜索ArXiv论文", "success": True},
            {"description": "搜索网络资源", "success": True},
            {"description": "生成研究计划", "success": True}
        ],
        "arxiv_papers": [
            {"title": "Deep Learning in Medical Imaging", "authors": ["John Smith", "Jane Doe"], "published": "2023-12-01"},
            {"title": "AI-Powered Diagnosis Systems", "authors": ["Li Zhang"], "published": "2023-11-15"}
        ],
        "web_search_results": [
            {"title": "最新AI医疗技术报告"},
            {"title": "医疗AI发展趋势分析"}
        ]
    }
    
    try:
        exporter = ProposalExporter(output_dir="output")
        
        # 打印详细字体状态
        print(f"字体目录: {exporter.font_dir}")
        print(f"中文字体可用: {exporter.chinese_font_available}")
        print(f"强制文本转换: {getattr(exporter, 'force_text_conversion', False)}")
        
        # 检查字体文件
        if os.path.exists(exporter.font_dir):
            font_files = os.listdir(exporter.font_dir)
            print(f"字体文件: {font_files}")
            for font_file in font_files:
                font_path = os.path.join(exporter.font_dir, font_file)
                if os.path.isfile(font_path):
                    print(f"  {font_file}: {os.path.getsize(font_path)} bytes")
        
        pdf_file = exporter.generate_pdf_report(test_result, "test_proposal.pdf")
        print(f"测试PDF已生成: {pdf_file}")
        
        # 验证PDF文件
        if os.path.exists(pdf_file):
            print(f"PDF文件大小: {os.path.getsize(pdf_file)} bytes")
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()