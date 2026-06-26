#!/usr/bin/env python3
"""
编辑 Word 文档 (.docx) - 查找替换、添加内容等

使用方法:
    python edit_docx.py --input document.docx --output edited.docx --find "old" --replace "new"
    python edit_docx.py -i report.docx -o updated.docx --add-text "新段落" --position end
    python edit_docx.py --input doc.docx --output new.docx --add-heading "新章节"
"""

import argparse
import sys
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH


def find_and_replace(input_file: str, output_file: str, find_text: str, replace_text: str) -> bool:
    """在 Word 文档中查找并替换文本"""
    try:
        doc = Document(input_file)
        count = 0
        
        # 替换段落中的文本
        for paragraph in doc.paragraphs:
            if find_text in paragraph.text:
                paragraph.text = paragraph.text.replace(find_text, replace_text)
                count += 1
        
        # 替换表格中的文本
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if find_text in paragraph.text:
                            paragraph.text = paragraph.text.replace(find_text, replace_text)
                            count += 1
        
        doc.save(output_file)
        print(f"✓ 查找替换完成")
        print(f"  查找：{find_text}")
        print(f"  替换：{replace_text}")
        print(f"  替换次数：{count}")
        print(f"  输出文件：{output_file}")
        return True
    
    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


def add_text_to_document(input_file: str, output_file: str, text: str, 
                         position: str = 'end', heading_level: int = None) -> bool:
    """在文档中添加文本"""
    try:
        doc = Document(input_file)
        
        if heading_level:
            doc.add_heading(text, level=heading_level)
        else:
            doc.add_paragraph(text)
        
        doc.save(output_file)
        print(f"✓ 文本已添加")
        print(f"  位置：{position}")
        print(f"  输出文件：{output_file}")
        return True
    
    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description='编辑 Word 文档 (.docx)')
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='输入 Word 文件路径'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出 Word 文件路径'
    )
    parser.add_argument(
        '--find', '-f',
        help='要查找的文本'
    )
    parser.add_argument(
        '--replace', '-r',
        help='替换为的文本'
    )
    parser.add_argument(
        '--add-text', '-a',
        help='要添加的文本'
    )
    parser.add_argument(
        '--position',
        choices=['start', 'end'],
        default='end',
        help='添加位置'
    )
    parser.add_argument(
        '--add-heading',
        help='添加标题'
    )
    parser.add_argument(
        '--heading-level',
        type=int,
        choices=[1, 2, 3],
        default=1,
        help='标题级别'
    )
    
    args = parser.parse_args()
    
    # 验证输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 错误：文件不存在 {input_path}")
        return 1
    
    if not input_path.suffix.lower() == '.docx':
        print(f"❌ 错误：输入文件不是 Word 文档")
        return 1
    
    success = False
    
    # 查找替换
    if args.find and args.replace:
        success = find_and_replace(args.input, args.output, args.find, args.replace)
    
    # 添加文本
    elif args.add_text:
        success = add_text_to_document(
            args.input, 
            args.output, 
            args.add_text,
            position=args.position
        )
    
    # 添加标题
    elif args.add_heading:
        success = add_text_to_document(
            args.input,
            args.output,
            args.add_heading,
            heading_level=args.heading_level
        )
    
    else:
        print("❌ 错误：必须指定 --find/--replace、--add-text 或 --add-heading")
        return 1
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
