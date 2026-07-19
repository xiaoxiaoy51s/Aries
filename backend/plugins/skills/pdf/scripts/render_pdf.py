#!/usr/bin/env python3
"""
把 PDF 页面渲染成 PNG 图片（用于视觉检查）

底层调用 Poppler 的 pdftoppm。若系统未安装 Poppler，会打印安装指引。

使用方法:
    python render_pdf.py -i input.pdf -o pages/
    python render_pdf.py -i input.pdf -o pages/ --first 1 --last 3
    python render_pdf.py -i input.pdf -o pages/ --dpi 200
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_pdftoppm() -> str | None:
    """在 PATH 中查找 pdftoppm，找不到返回 None。"""
    return shutil.which("pdftoppm")


def render(
    pdf_path: Path,
    out_dir: Path,
    first: int | None,
    last: int | None,
    dpi: int,
    fmt: str,
) -> list[Path]:
    """调用 pdftoppm 渲染，返回生成的 PNG 文件列表。"""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 输出前缀：out_dir/pdf_path.stem
    prefix = out_dir / pdf_path.stem
    cmd = ["pdftoppm", f"-{fmt}", "-r", str(dpi)]
    if first is not None:
        cmd += ["-f", str(first)]
    if last is not None:
        cmd += ["-l", str(last)]
    cmd += [str(pdf_path), str(prefix)]

    try:
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        _print_install_hint()
        sys.exit(2)

    if result.returncode != 0:
        print(
            f"ERROR: pdftoppm failed (exit {result.returncode}):\n{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    # pdftoppm 输出 <prefix>-N.<ext> 或 <prefix>-NN.<ext>
    pattern = f"{pdf_path.stem}-*.{fmt}"
    pages = sorted(out_dir.glob(pattern))
    return pages


def _print_install_hint():
    print(
        "ERROR: pdftoppm (Poppler) is not installed.\n"
        "Install with:\n"
        "  macOS:  brew install poppler\n"
        "  Ubuntu/Debian: sudo apt-get install -y poppler-utils\n"
        "  Windows: download from https://github.com/oschwartz10612/poppler-windows/releases\n"
        "           and add its Library\\bin to PATH",
        file=sys.stderr,
    )


def build_arg_parser():
    p = argparse.ArgumentParser(description="把 PDF 渲染为 PNG/JPEG 图片")
    p.add_argument("--input", "-i", required=True, help="输入 PDF 文件路径")
    p.add_argument(
        "--output",
        "-o",
        required=True,
        help="输出目录（存放 page PNG 文件）",
    )
    p.add_argument("--first", type=int, help="起始页码（1-based）")
    p.add_argument("--last", type=int, help="结束页码（1-based）")
    p.add_argument("--dpi", type=int, default=150, help="分辨率 DPI（默认 150）")
    p.add_argument(
        "--format",
        choices=("png", "jpeg"),
        default="png",
        help="输出图片格式（默认 png）",
    )
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    pdf_path = Path(args.input)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output)

    if find_pdftoppm() is None:
        _print_install_hint()
        sys.exit(2)

    pages = render(
        pdf_path,
        out_dir,
        args.first,
        args.last,
        args.dpi,
        args.format,
    )

    if not pages:
        print("WARNING: no output files were produced.", file=sys.stderr)
        sys.exit(1)

    print(f"OK: rendered {len(pages)} page(s) to {out_dir}")
    for p in pages:
        print(f"  {p.name} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
