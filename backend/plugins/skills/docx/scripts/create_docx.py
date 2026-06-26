#!/usr/bin/env python3
"""
创建 Word 文档 (.docx)

使用方法:
    python create_docx.py --text "Hello World" --output hello.docx
    python create_docx.py --input content.md --output document.docx --format markdown
    python create_docx.py --title "报告标题" --output report.docx --sections 3
"""

import argparse
import sys
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn


def _set_default_fonts(doc):
    """设置文档默认字体：正文宋体、标题黑体、西文新罗马"""
    try:
        # 正文样式
        style = doc.styles['Normal']
        rpr = style._element.get_or_add_rPr()
        rFonts = rpr.get_or_add_rFonts()
        rFonts.set(qn('w:eastAsia'), '宋体')
        rFonts.set(qn('w:ascii'), 'Times New Roman')
        rFonts.set(qn('w:hAnsi'), 'Times New Roman')
        rFonts.set(qn('w:cs'), 'Times New Roman')
    except Exception:
        pass

    # 设置标题样式字体
    for level in range(0, 10):
        try:
            style_name = f'Heading {level}' if level > 0 else 'Title'
            if style_name in doc.styles:
                style = doc.styles[style_name]
                rpr = style._element.get_or_add_rPr()
                rFonts = rpr.get_or_add_rFonts()
                rFonts.set(qn('w:eastAsia'), '黑体')
                rFonts.set(qn('w:ascii'), 'Times New Roman')
                rFonts.set(qn('w:hAnsi'), 'Times New Roman')
                rFonts.set(qn('w:cs'), 'Times New Roman')
        except Exception:
            pass


def _apply_run_fonts(run):
    """为单个 run 设置字体"""
    try:
        rpr = run._element.get_or_add_rPr()
        rFonts = rpr.get_or_add_rFonts()
        rFonts.set(qn('w:eastAsia'), '宋体')
        rFonts.set(qn('w:ascii'), 'Times New Roman')
        rFonts.set(qn('w:hAnsi'), 'Times New Roman')
        rFonts.set(qn('w:cs'), 'Times New Roman')
    except Exception:
        pass


def create_docx_from_text(text: str, output_path: str, title: str = None):
    """从纯文本创建 Word 文档"""
    doc = Document()
    _set_default_fonts(doc)

    # 添加标题
    if title:
        heading = doc.add_heading(title, level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in heading.runs:
            _apply_run_fonts(run)

    # 处理文本内容
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            doc.add_paragraph()
            continue

        # 检测是否是标题
        if line.startswith('# '):
            h = doc.add_heading(line[2:].strip(), level=1)
            for run in h.runs:
                _apply_run_fonts(run)
        elif line.startswith('## '):
            h = doc.add_heading(line[3:].strip(), level=2)
            for run in h.runs:
                _apply_run_fonts(run)
        elif line.startswith('### '):
            h = doc.add_heading(line[4:].strip(), level=3)
            for run in h.runs:
                _apply_run_fonts(run)
        else:
            p = doc.add_paragraph(line)
            for run in p.runs:
                _apply_run_fonts(run)

    doc.save(output_path)
    print(f"✓ Word 文档已创建：{output_path}")


def create_docx_from_markdown(markdown_text: str, output_path: str, title: str = None):
    """从 Markdown 创建 Word 文档"""
    doc = Document()
    _set_default_fonts(doc)

    # 添加标题
    if title:
        heading = doc.add_heading(title, level=0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in heading.runs:
            _apply_run_fonts(run)

    lines = markdown_text.split('\n')
    i = 0

    def _is_bullet(raw_line: str) -> bool:
        stripped = raw_line.lstrip()
        return stripped.startswith('- ') or stripped.startswith('* ')

    def _bullet_text(raw_line: str) -> str:
        return raw_line.lstrip()[2:].strip()

    def _heading_level(raw_line: str) -> int | None:
        stripped = raw_line.lstrip()
        if stripped.startswith('### '):
            return 3
        if stripped.startswith('## '):
            return 2
        if stripped.startswith('# '):
            return 1
        return None

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        heading_level = _heading_level(raw)
        if heading_level is not None:
            prefix_len = 2 + heading_level
            h = doc.add_heading(raw.lstrip()[prefix_len:].strip(), level=heading_level)
            for run in h.runs:
                _apply_run_fonts(run)
            i += 1
            continue

        if _is_bullet(raw):
            list_items = []
            while i < len(lines) and _is_bullet(lines[i]):
                list_items.append(_bullet_text(lines[i]))
                i += 1
            for item in list_items:
                p = doc.add_paragraph(style='List Bullet')
                run = p.add_run(item)
                _apply_run_fonts(run)
            continue

        if line.startswith('```'):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                i += 1
            if i < len(lines):
                i += 1
            continue

        if line.startswith('|'):
            i += 1
            continue

        if not line:
            doc.add_paragraph()
            i += 1
            continue

        para_lines = []
        while i < len(lines):
            current = lines[i]
            current_stripped = current.strip()
            if not current_stripped:
                break
            if _heading_level(current) is not None or current_stripped.startswith('|') or current_stripped.startswith('```'):
                break
            if _is_bullet(current):
                break
            para_lines.append(current_stripped)
            i += 1

        if para_lines:
            p = doc.add_paragraph(' '.join(para_lines))
            for run in p.runs:
                _apply_run_fonts(run)
        else:
            i += 1

    doc.save(output_path)
    print(f"✓ Word 文档已创建：{output_path}")


def create_simple_docx(output_path: str, title: str = None, sections: int = 0):
    """创建简单的 Word 文档结构"""
    doc = Document()
    _set_default_fonts(doc)

    # 添加标题
    if title:
        h = doc.add_heading(title, level=0)
        for run in h.runs:
            _apply_run_fonts(run)

    # 添加示例章节
    for i in range(1, sections + 1):
        h = doc.add_heading(f'第{i}章', level=1)
        for run in h.runs:
            _apply_run_fonts(run)
        p = doc.add_paragraph(f'这是第{i}章的内容。')
        for run in p.runs:
            _apply_run_fonts(run)

    doc.save(output_path)
    print(f"✓ Word 文档已创建：{output_path}")


def main():
    parser = argparse.ArgumentParser(description='创建 Word 文档 (.docx)')
    parser.add_argument('--input', '-i', help='输入文件路径（.txt, .md）')
    parser.add_argument('--output', '-o', required=True, help='输出 Word 文件路径')
    parser.add_argument('--text', '-t', help='直接输入的文本内容')
    parser.add_argument('--title', default='', help='文档标题')
    parser.add_argument('--format', choices=['text', 'markdown'], default='text', help='输入格式')
    parser.add_argument('--sections', type=int, default=0, help='创建章节数量')

    args = parser.parse_args()

    try:
        if args.input:
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"❌ 错误：文件不存在 {input_path}")
                return 1

            content = input_path.read_text(encoding='utf-8')

            if args.format == 'markdown':
                create_docx_from_markdown(content, args.output, args.title)
            else:
                create_docx_from_text(content, args.output, args.title)

        elif args.text:
            if args.format == 'markdown':
                create_docx_from_markdown(args.text, args.output, args.title)
            else:
                create_docx_from_text(args.text, args.output, args.title)

        elif args.sections > 0:
            create_simple_docx(args.output, args.title, args.sections)

        else:
            print("❌ 错误：必须指定 --input 文件、--text 内容或 --sections")
            return 1

        return 0

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
