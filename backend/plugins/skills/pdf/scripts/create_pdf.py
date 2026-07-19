#!/usr/bin/env python3
"""
创建 PDF 文档

使用方法:
    python create_pdf.py --text "Hello World" --output hello.pdf
    python create_pdf.py --input content.md --output document.pdf --format markdown
    python create_pdf.py --title "报告标题" --output report.pdf --text "正文内容"
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        PageBreak,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print(
        "ERROR: reportlab is not installed. Install with:\n"
        "  uv pip install reportlab\n"
        "or\n  python -m pip install reportlab",
        file=sys.stderr,
    )
    sys.exit(2)


# ---------- 字体注册（中文友好） ----------

def _register_cjk_font():
    """尝试注册一个可用的中文字体，失败则回退到内置 Helvetica。"""
    candidates = [
        # Windows
        ("C:/Windows/Fonts/msyh.ttc", "MSYH"),
        ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
        ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
        # macOS
        ("/System/Library/Fonts/PingFang.ttc", "PingFang"),
        ("/System/Library/Fonts/STHeiti Light.ttc", "STHeiti"),
        # Linux (常见)
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoCJK"),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WQYMicrohei"),
    ]
    for path, name in candidates:
        try:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont(name, path))
                return name
        except Exception:
            continue
    return None  # 未找到，调用方用默认字体


# ---------- Markdown 简易解析 ----------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")


def _markdown_to_flowables(text, styles, cjk_font):
    """把 Markdown 文本转成 reportlab flowables（段落/标题/列表）。"""
    flow = []
    body_style = styles["Normal"]
    h1 = styles.get("Heading1")
    h2 = styles.get("Heading2")
    h3 = styles.get("Heading3")

    # 若有中文字体，替换正文与标题的 typeface
    if cjk_font:
        for s in (body_style, h1, h2, h3):
            if s is not None:
                try:
                    s.fontName = cjk_font
                except Exception:
                    pass

    lines = text.splitlines()
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flow.append(Spacer(1, 0.3 * cm))
            continue

        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text_content = m.group(2).strip()
            # 转义 reportlab 段落里的特殊字符
            text_content = _escape(text_content)
            style = {1: h1, 2: h2, 3: h3}.get(level, h3)
            if style is not None:
                flow.append(Paragraph(text_content, style))
                flow.append(Spacer(1, 0.2 * cm))
            continue

        m = _BULLET_RE.match(line)
        if m:
            item = _escape(m.group(1).strip())
            bullet_style = ParagraphStyle(
                "Bullet",
                parent=body_style,
                leftIndent=0.8 * cm,
                bulletIndent=0.3 * cm,
            )
            flow.append(Paragraph(f"• {item}", bullet_style))
            continue

        m = _QUOTE_RE.match(line)
        if m:
            quote = _escape(m.group(1).strip())
            quote_style = ParagraphStyle(
                "Quote",
                parent=body_style,
                leftIndent=1.0 * cm,
                textColor="#666666",
            )
            flow.append(Paragraph(quote, quote_style))
            continue

        # 普通段落
        flow.append(Paragraph(_escape(line), body_style))
    return flow


def _escape(text: str) -> str:
    """转义 reportlab Paragraph 里的 XML 特殊字符。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------- 主入口 ----------

def build_arg_parser():
    p = argparse.ArgumentParser(description="创建 PDF 文档")
    p.add_argument("--text", "-t", help="直接输入文本内容")
    p.add_argument("--input", "-i", help="输入文件路径 (.txt/.md)")
    p.add_argument("--output", "-o", required=True, help="输出 PDF 文件路径")
    p.add_argument("--title", help="文档标题（首页顶部）")
    p.add_argument(
        "--format",
        choices=("text", "markdown"),
        default="text",
        help="输入格式（默认 text）",
    )
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    # 获取文本内容
    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
            sys.exit(1)
        content = in_path.read_text(encoding="utf-8")
        fmt = args.format
    elif args.text is not None:
        content = args.text
        fmt = args.format
    else:
        print("ERROR: one of --text or --input is required", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 注册中文字体
    cjk_font = _register_cjk_font()

    # 构建文档
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=args.title or out_path.stem,
    )

    styles = getSampleStyleSheet()
    # 自定义正文样式：略大行距，便于阅读
    body = styles["Normal"]
    body.fontSize = 11
    body.leading = 16
    body.alignment = TA_LEFT

    flow = []

    # 标题
    if args.title:
        title_style = styles["Title"]
        if cjk_font:
            try:
                title_style.fontName = cjk_font
            except Exception:
                pass
        flow.append(Paragraph(_escape(args.title), title_style))
        flow.append(Spacer(1, 0.6 * cm))

    # 正文
    if fmt == "markdown":
        flow.extend(_markdown_to_flowables(content, styles, cjk_font))
    else:
        # 纯文本：按行生成段落
        normal = styles["Normal"]
        if cjk_font:
            try:
                normal.fontName = cjk_font
            except Exception:
                pass
        for line in content.splitlines():
            if not line.strip():
                flow.append(Spacer(1, 0.3 * cm))
                continue
            flow.append(Paragraph(_escape(line), normal))

    if not flow:
        flow.append(Paragraph("(empty document)", styles["Normal"]))

    doc.build(flow)
    print(f"OK: created {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
