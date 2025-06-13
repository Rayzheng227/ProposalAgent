%
%   This is file `phdproposal.cls',
%	@author andy123t
% 	@date 2020/12/16
%   This template for PhD proposal
%

% ---------- 定义的新的Class ----------
\ProvidesClass{phdproposal}[2021/11/29 v2.0.0]
\NeedsTeXFormat{LaTeX2e}


% ---------- 载入学校logo ----------
% \def\logopic{univ.eps}   %logo
% \DeclareOption{UnivLogo} {
% 	\def\logopic{univ.eps}
% }
% \ProcessOptions\relax


% ---------- 载入Class ----------
\LoadClass[a4paper,openany,twoside]{book}


% ---------- 中文字体宏包 ----------
\RequirePackage[cs4size,UTF8]{ctex}


% --------- 定义不同编译方式 ----------
\RequirePackage{ifpdf,ifxetex}
\ifxetex
  \RequirePackage{fontspec}
  \RequirePackage{graphicx}
\else
  \ifpdf
  	\usepackage[utf8]{inputenc}
  	\RequirePackage[T1]{fontenc}
    \RequirePackage{graphicx}
    \RequirePackage{epstopdf}
  \else
    \RequirePackage[dvipdfmx]{graphicx}
    \RequirePackage{bmpsize}
  \fi
\fi


% ---------- 定义页边距 ----------
\RequirePackage{geometry}
\geometry{left=2.5cm,right=2.5cm,top=1.7cm,bottom=1.8cm,includehead,includefoot}
\setlength{\headheight}{15pt}
%\addtolength{\headsep}{-0.1cm}     % 页眉位置
%\addtolength{\footskip}{-0.1cm}    % 页脚位置


% ---------- 常用宏包 ----------
\RequirePackage{amsmath,amssymb,amsthm,amsfonts}  % AMS公式
\RequirePackage{bm}         % 数学公式黑斜体
\RequirePackage{mathrsfs}   % 数学英文花体
\RequirePackage{booktabs}
\RequirePackage{float}
\RequirePackage{longtable}  % 长表格
\RequirePackage{multirow}   % 表格多行合并
\RequirePackage{enumerate}  % 改变列表标号样式
\RequirePackage{color,xcolor}
\RequirePackage{fancyhdr}
\RequirePackage{setspace}
\RequirePackage{tikz}       % 绘制图形
\RequirePackage{titlesec}   % 设置标题样式
\RequirePackage{tabularx}
\RequirePackage{makecell}
\RequirePackage{xstring}    % 使用条件语句


% --------设置图片的路径 ---------
\graphicspath{{./figure/}{./figures/}{./image/}{./images/}}



% ---------- 定义章节的编号格式 ----------
% \renewcommand{\chaptername}{\arabic{chapter}}
\renewcommand{\thechapter}{\chinese{chapter}、}
\renewcommand{\thesection}{\arabic{section}.}
\renewcommand{\thesubsection}{\arabic{section}.\arabic{subsection}}
\renewcommand{\thesubsubsection}{(\arabic{subsubsection})}


%---------- 定义章节标题格式 ------------
\titleformat{\chapter}[hang]{\normalfont \bfseries \Large \filcenter}
    {\Large \thechapter}{4pt}{}
\titlespacing{\chapter}{0pt}{0ex  plus .1ex minus .2ex}{2.5ex plus .1ex minus .2ex}

\titleformat{\section}[hang]{\bfseries \zihao{-3}}
    {\zihao{-3} \thesection}{8pt}{}
\titlespacing{\section}{0pt}{1.5ex plus .1ex minus .2ex}{1.5ex plus .1ex minus .2ex}

\titleformat{\subsection}[hang]{\bfseries \zihao{4}}
    {\zihao{4} \thesubsection}{6pt}{}
\titlespacing{\subsection}%
    {0pt}{1.5ex plus .1ex minus .2ex}{\wordsep}

\titleformat{\subsubsection}[hang]{\heiti}
    {\thesubsubsection }{1em}{}{}
\titlespacing{\subsubsection}%
    {0pt}{1.2ex plus .1ex minus .2ex}{\wordsep}




%---------- 设置章节目录的深度 -------------
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{3} 


% ------------- 设置附录 -----------
\RequirePackage{titletoc}
\RequirePackage[title,titletoc]{appendix}
%\renewcommand{\appendixname}{附录}

%-------------- 定义页眉页脚 -------------------

% 定义页眉和页脚 使用fancyhdr 宏包
\newcommand{\makeheadrule}{%
    \makebox[-3pt][l]{\rule[.7\baselineskip]{\headwidth}{0.4pt}}
    \rule[0.85\baselineskip]{\headwidth}{1.2pt}\vskip-.8\baselineskip
    }

\makeatletter
\renewcommand{\headrule}{%
    {\if@fancyplain\let\headrulewidth\plainheadrulewidth\fi
     \makeheadrule}}

% ------------ 画单隔线 ------------
% \renewcommand{\headrulewidth}{0.5pt}    % 在页眉下画一个0.5pt宽的分隔线
% \renewcommand{\footrulewidth}{0pt}      % 在页脚不画分隔线。


% ------------ 设置页眉样式 -----------
\newcommand{\headstyle}{
	% \fancyhead[R]{\color{black}\fangsong \leftmark}
	% \fancyhead[L]{\color{black} 上海师范大学硕士论文}
	% \fancyhead[RO,LE]{\color{black}\zihao{5} \leftmark}
	% \fancyhead[LO,RE]{\color{black} \zihao{5} 攻博研修计划书}
	\fancyhead[C]{\fangsong \zihao{5} 研究计划书}
}


% ------- 设置页脚样式 ----------
\newcommand{\footstyle}{\fancyfoot[C]{\fangsong \thepage}}
\pagestyle{empty}
\pagestyle{fancy}
\fancyhf{} %清空原有样式
\headstyle
\footstyle


% ------ 定义一种新的格式叫做main ------------
\fancypagestyle{main}{%
    \pagestyle{fancyplain} 
	\fancyhf{} %清空原有样式
	\headstyle
	\footstyle
}


\renewcommand\chaptermark[1]{%
  \markboth{%
    \ifnum \c@secnumdepth >\m@ne
      \if@mainmatter
        \@chapapp\ \ %
      \fi
    \fi
    #1}{}%
}


% ----------- 中文段落缩进和行距 ------------
\setlength{\parindent}{2em}                 % 首行两个汉字的缩进量
\setlength{\parskip}{3pt plus1pt minus1pt}  % 段落之间的竖直距离
\renewcommand{\baselinestretch}{1.35}        % 定义行距
%\topskip=15pt   % 书写区域顶部空白
%\parskip=5pt
%\parindent=0pt
%\baselineskip=5pt
%\setlength{\baselineskip}{24pt}


% ------------------- 浮动对象设置 ---------------------
% 浮动对象的缺省值稍微宽松一点，从而防止幅度对象占据过多的文本页面
% 也可以防止在很大空白的浮动页上放置很小的图形
\renewcommand{\textfraction}{0.15}
\renewcommand{\topfraction}{0.85}
\renewcommand{\bottomfraction}{0.65}
\renewcommand{\floatpagefraction}{0.60}


% ---------------- 设置图表格式 ---------------

% \renewcommand{\thetable}{\arabic{chapter}.\arabic{table}}
% \renewcommand{\theequation}{\arabic{chapter}.\arabic{equation}}
% \renewcommand{\thefigure}{\arabic{chapter}.\arabic{figure}}
\renewcommand{\thetable}{\arabic{table}}
\renewcommand{\theequation}{\arabic{equation}}
\renewcommand{\thefigure}{\arabic{figure}}


% --------- 定制图形和表格标题的样式 --------------
\RequirePackage{caption}
\captionsetup{font={normalsize,singlespacing},labelformat={default},labelsep=quad}
\captionsetup[figure]{position=bottom,skip={5pt},name={图}}
\captionsetup[table]{position=top,skip={2pt},name={表}}
\setlength{\textfloatsep}{0pt}
\setlength{\floatsep}{10pt plus 3pt minus 2pt}
\setlength{\intextsep}{10pt}
\setlength{\abovecaptionskip}{2pt plus1pt minus1pt}
\setlength{\belowcaptionskip}{3pt plus1pt minus2pt}
%\setlength{\itemsep}{3pt plus1pt minus2pt}


% ----- 重新设置图表autoref -------
\newcommand{\figureautorefname}{图}
\newcommand{\tableautorefname}{表}


% --- 使用tabularx库并定义新的左右中格式 ----
\newcolumntype{L}{X}
\newcolumntype{C}{>{\centering \arraybackslash}X}
\newcolumntype{R}{>{\raggedright \arraybackslash}X}
\newcolumntype{P}[1]{>{\centering \arraybackslash}p{#1}}

% ------------ 设置三线表格式 ------
% \setlength{\heavyrulewidth}{1.5pt}
% \setlength{\lightrulewidth}{0.5pt}
% \setlength{\cmidrulewidth}{0.5pt}
% \setlength{\aboverulesep}{0pt}
% \setlength{\belowrulesep}{0pt}
% \setlength{\abovetopsep}{0pt}
% \setlength{\belowbottomsep}{0pt}


% -------- 重新定义图和表的浮动环境 ---------
\newenvironment{generalfig}[3][htbp]{
	\def \figcaption {#2}
	\def \figlabel {#3}
	\begin{figure}[#1]
		\centering
	}{
		\caption{\figcaption} \label{\figlabel}
	\end{figure}
}
\newenvironment{generaltab}[3][htbp]{
	\def \tabcaption {#2}
	\def \tablabel {#3}
	\begin{table}[#1]
		\caption{\tabcaption} \label{\tablabel}
		\zihao{5}
		\centering
	}{
	\end{table}
}


%------------- 数学定理设置 ---------------
\theoremstyle{plain} 
\newtheorem{definition}{\heiti 定义}
\newtheorem{proposition}{\heiti 命题}
\newtheorem{lemma}{\heiti 引理}
\newtheorem{theorem}{\heiti 定理}
\newtheorem{example}{\heiti 例}
\newtheorem{corollary}{\heiti 推论}
\newtheorem{remark}{\heiti 注}
\renewcommand{\proofname}{\heiti 证明}
%\renewcommand{\qedsymbol}{$\blacksquare$}
%\newtheorem{algorithm}{算法}
%\newtheorem{axiom}{公理}
%\newtheorem{property}{性质}
%\newtheorem{assumption}{假设}


% -------------- 数学公式设置 ---------------
\allowdisplaybreaks[4]   % \eqnarray 如果很长，影响分栏、换行和分页

% ----- 设置公式间距为零 ------
\AtBeginDocument{
	\setlength{\abovedisplayskip}{4pt}
	\setlength{\belowdisplayskip}{4pt}
	\setlength{\abovedisplayshortskip}{2pt}
	\setlength{\belowdisplayshortskip}{2pt}
	\setlength{\arraycolsep}{2pt}   % array中列之间空白长度
}

% ------- 公式编号带章节 ----------
% \numberwithin{equation}{chapter}

% 重新设置公式autoref
\newcommand{\equationautorefname}{等式}


% ---- 定义列表项的样式 -----

\RequirePackage{enumitem}
%\setlist{noitemsep}
\setitemize{itemsep=3pt}


%------------- 定义新的标题页面 -------------------

% ------ 添加几个新的文档属性 ------
\def \defschool {}
\def \defcollege {}
\def \defmajor {}
\def \defstudy {}
\def \definstructor {}
\def \defsuptitle {}

\newcommand{\school}[1]{\def \defschool {#1}}
\newcommand{\college}[1]{\def \defcollege {#1}}
\newcommand{\major}[1]{\def \defmajor {#1}}
\newcommand{\study}[1]{\def \defstudy {#1}}
\newcommand{\instructor}[1]{\def \definstructor {#1}}
\newcommand{\suptitle}[1]{\def \defsuptitle {#1}}

% ------- 重置命令 maketitle -------
\renewcommand{\maketitle}[1][12em]{
	\begin{titlepage}
		\begin{center}
			% 添加logo位置
			\vspace*{2cm}
			% 检查logo文件是否存在
			\IfFileExists{figures/Logo.png}{%
				\includegraphics[width=4cm]{figures/Logo.png}%
			}{%
				\IfFileExists{Logo.png}{%
					\includegraphics[width=4cm]{Logo.png}%
				}{%
					% 如果没有logo文件，显示占位符或留空
					\vspace{4cm}%
				}%
			}
			
			\vspace{2cm}
			{\zihao{2}\bfseries {\defsuptitle}}\\ %\bfseries
			\vspace{0.5cm}
			\begin{center}
			\parbox[t]{15cm}{\centering \zihao{1} \heiti \@title}
			\end{center}
			\vspace{4cm}
			{\zihao{3} \heiti
				\renewcommand\arraystretch{1.5}
				\begin{tabular}{lc}
					\makebox[4em][s]{作\hfill 者~：} & 
					\underline{\makebox[#1]{\songti \@author}} \\
					\makebox[4em][s]{时\hfill 间~：} &
					\underline{\makebox[#1]{\songti \@date}} \\
				\end{tabular}}\\
		\end{center}
	\end{titlepage}
}



% ------------ 定义新的声明页面 --------------

% 定义三个条件语句
% \newcommand{\encryption}[1]{
% 	\IfStrEqCase{#1}{{empty}{$\square$}
% 		{true}{$\text{\rlap{\checkmark}}\square$ }
% 		{false}{$\square$}}
% 	[$\square$]
% }
% \newcommand{\nonencryption}[1]{
% 	\IfStrEqCase{#1}{{empty}{$\square$}
% 		{true}{$\square$}
% 		{false}{$\text{\rlap{\checkmark}}\square$}}
% 	[$\square$]
% }
% \newcommand{\encryptionyear}[2]{
% 	\IfStrEqCase{#1}{{empty}{}
% 		{true}{#2}
% 		{false}{}}
% }


% ------------------ 中文摘要环境 -------------
\newenvironment{cnabstract}[1]{
	\def \cnkeyword {#1}
	\clearpage
	\phantomsection
	\addcontentsline{toc}{chapter}{摘~要}
	\chaptermark{摘~~要}
	\vspace*{-2ex}
	\begin{center} \heiti \Large 摘~~~~要 \end{center}
	\vspace*{3ex}
}{
	\vspace{2ex}
	{\noindent \heiti 关键词：} \cnkeyword
	\clearpage
}


% ----------------- 英文摘要环境 ----------------
\newenvironment{enabstract}[1]{
	\def \enkeyword {#1}
	\clearpage
	\phantomsection
	\addcontentsline{toc}{chapter}{\textbf{Abstract}}
	\chaptermark{Abstract}
	\vspace*{-3ex}
	\begin{center} \Large \bfseries Abstract \end{center} 
	\vspace*{3ex}
}{
	\vspace*{2ex}
	{\noindent \bfseries Key Words: } \enkeyword
	\clearpage
}



% ------------- 定义新的目录页面 ----------------

% \renewcommand{\thechapter}{\chinese{chapter}、}
\RequirePackage{tocloft}
\RequirePackage{hyperref}
\hypersetup{
	colorlinks = true,
	linkcolor  = black,
	citecolor = black
} % 去掉目录红框
\renewcommand{\cfttoctitlefont}{\hfill \heiti \Large}
\renewcommand{\contentsname}{目~~录}
\renewcommand{\cftchapaftersnumb}{\hspace{1.2ex}}
\renewcommand{\cftaftertoctitle}{\hfill}
\setlength{\cftbeforetoctitleskip}{2ex}
\setlength{\cftaftertoctitleskip}{5ex}
\renewcommand{\cftsecaftersnumb}{\hspace{-2ex}}
\renewcommand{\cftsubsecaftersnumb}{\hspace{-2.5ex}}
\renewcommand{\cftsecdotsep}{\cftdotsep}  % 设置Section引导点
\renewcommand\cftbeforechapskip{2.5ex}
\renewcommand{\cftbeforesecskip}{1.5ex} % 设置Part字体
\renewcommand{\cftsecfont}{\songti}   % 设置Section字体

% 使用条件语句
\RequirePackage{xstring}

% 定义两个新语句
% 第一个语句更改fancyhdr样式
\newcommand{\plainfooterstyle}[1]{
	\IfStrEqCase{#1}{{nopagenum}{}
		{pagenum}{\footstyle}
		{pagenumtoc}{\footstyle}}
}
% 第二个语句在目录中添加目录标签
\newcommand{\addtoctotoc}[1]{
	\IfStrEqCase{#1}{{nopagenum}{}
		{pagenum}{}
		{pagenumtoc}{\phantomsection
			\addcontentsline{toc}{chapter}{目~录}}}
}


% ----------- 设置新的生成目录命令 -------------
\let \oldtableofcontens \tableofcontents
\newcommand{\maketoc}[1][nopagenum]{
	% 修改hdr原plain格式
	\fancypagestyle{plain}{%
		\fancyhf{} %清空原有样式
		\headstyle
		\plainfooterstyle{#1}
	}
	% 设置目录hdr和页码选项
	\clearpage
	\pagestyle{plain}
	\addtoctotoc{#1}
	\tableofcontents
	\clearpage
	\pagestyle{main}
}


% ----------- 重新定义参考文献页 -----------
%\bibliographystyle{plain}
\ctexset{bibname={参考文献}}

% 设置新的附录命令
\let \oldbibliography \bibliography
\renewcommand{\bibliography}[1]{
	% 添加到目录
	\clearpage
	\phantomsection
	\addcontentsline{toc}{chapter}{参考文献}
	\oldbibliography{#1}
}



% End of file `phdproposal.cls'.

