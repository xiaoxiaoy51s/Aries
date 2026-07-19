#!/usr/bin/env python3
"""
从 PDF 提取文本、表格或元数据

使用方法:
    python extract_pdf.py -i input.pdf -o output.txt
    python extract_pdf.py -i input.pdf --meta
    python extract_pdf.py -i input.pdf --tables -o tables.csv
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print(
        "ERROR: pdfplumber is not installed. Install with:\n"
        "  uv pip install pdfplumber\n"
        "or\n  python -m pip install pdfplumber",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError:
        PdfReader = None  # 元数据提取降级


def extract_text(pdf_path: Path, out_path: Path | None) -> None:
    """提取所有页面文本。"""
    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            parts.append(f"===== Page {i} =====\n{text}\n")
    result = "\n".join(parts)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result, encoding="utf-8")
        print(f"OK: extracted {len(parts)} pages to {out_path}")
    else:
        sys.stdout.write(result)


def extract_tables(pdf_path: Path, out_path: Path) -> None:
    """提取所有表格为单个 CSV（每张表前加 page/table 标记行）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with pdfplumber.open(str(pdf_path)) as pdf, out_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as fp:
        writer = csv.writer(fp)
        for page_idx, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables() or []
            for tbl_idx, tbl in enumerate(tables, 1):
                if not tbl:
                    continue
                writer.writerow([f"--- page {page_idx} / table {tbl_idx} ---"])
                for row in tbl:
                    writer.writerow([c if c is not None else "" for c in row])
                writer.writerow([])
                total += 1
    print(f"OK: extracted {total} table(s) to {out_path}")


def print_metadata(pdf_path: Path) -> None:
    """打印 PDF 元数据。"""
    if PdfReader is None:
        # 降级：用 pdfplumber 的 .metadata
        with pdfplumber.open(str(pdf_path)) as pdf:
            meta = pdf.metadata or {}
        print(f"Path: {pdf_path}")
        print(f"Pages: {len(pdf.pages)}")
        for k, v in meta.items():
            print(f"{k}: {v}")
        return

    reader = PdfReader(str(pdf_path))
    print(f"Path: {pdf_path}")
    print(f"Pages: {len(reader.pages)}")
    meta = reader.metadata or {}
    for k, v in meta.items():
        print(f"{k}: {v}")


def build_arg_parser():
    p = argparse.ArgumentParser(description="从 PDF 提取文本/表格/元数据")
    p.add_argument("--input", "-i", required=True, help="输入 PDF 文件路径")
    p.add_argument("--output", "-o", help="输出文件路径（不指定则输出到 stdout）")
    p.add_argument("--tables", action="store_true", help="提取表格为 CSV")
    p.add_argument("--meta", action="store_true", help="仅打印元数据")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    pdf_path = Path(args.input)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if args.meta:
        print_metadata(pdf_path)
        return

    if args.tables:
        out_path = Path(args.output) if args.output else Path("tables.csv")
        extract_tables(pdf_path, out_path)
        return

    out_path = Path(args.output) if args.output else None
    extract_text(pdf_path, out_path)


if __name__ == "__main__":
    main()
