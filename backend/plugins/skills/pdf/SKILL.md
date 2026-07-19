---
name: pdf
description: "Use this skill any time a PDF file is the primary input or output. This means any task where the user wants to: open, read, extract text or tables from an existing .pdf file; create a new PDF from scratch from text, Markdown, or structured data; render PDF pages to images for visual review; inspect or verify PDF layout, fonts, or embedded media; or convert between PDF and other formats. Trigger especially when the user references a PDF file by name or path - even casually (like \"the pdf in my downloads\") - and wants something done to it or produced from it. Also trigger when the durable output or target is a PDF file and visual layout fidelity matters. Do NOT trigger when the primary deliverable is a Word document, spreadsheet, HTML report, or standalone Python script, even if PDF is involved as an intermediate format."
---

# PDF creation, reading, rendering, and verification

## Overview

A PDF is a fixed-layout document format. This skill provides three script-driven
workflows (create / extract / render) plus guidance for visual verification.

## Quick Reference

**IMPORTANT: Always use the FULL PATH to scripts. Never write PDF generation code yourself when a script already covers the task.**

| Task | Script | Full Command |
|------|--------|--------------|
| **Create from text/Markdown** | `create_pdf.py` | `python d:/agent/aries/backend/plugins/skills/pdf/scripts/create_pdf.py -t "Hello" -o hello.pdf` |
| **Extract text/tables** | `extract_pdf.py` | `python d:/agent/aries/backend/plugins/skills/pdf/scripts/extract_pdf.py -i input.pdf -o out.txt` |
| **Render pages to PNG** | `render_pdf.py` | `python d:/agent/aries/backend/plugins/skills/pdf/scripts/render_pdf.py -i input.pdf -o pages/` |
| Read metadata | `extract_pdf.py` | `python d:/agent/aries/backend/plugins/skills/pdf/scripts/extract_pdf.py -i input.pdf --meta` |
| Extract tables | `extract_pdf.py` | `python d:/agent/aries/backend/plugins/skills/pdf/scripts/extract_pdf.py -i input.pdf --tables -o tables.csv` |

---

## When To Use

- Read or review PDF content where layout and visuals matter.
- Create PDFs programmatically with reliable formatting.
- Validate final rendering before delivery.
- Extract text or tables from existing PDFs.

## Workflow

1. **Prefer visual review**: render PDF pages to PNGs and inspect them.
   - Use the bundled `render_pdf.py` (wraps Poppler's `pdftoppm`) or system Poppler when available.
   - If unavailable, install Poppler or ask the user to review the output locally.
2. **Use `create_pdf.py`** (backed by `reportlab`) to generate PDFs when creating new documents.
3. **Use `extract_pdf.py`** (backed by `pdfplumber` + `pypdf`) for text extraction, table extraction, and metadata quick checks; do not rely on text extraction for layout fidelity.
4. After each meaningful update, re-render pages and verify alignment, spacing, and legibility.

## Temp And Output Conventions

- Use `tmp/pdfs/` for intermediate files; delete them when done.
- Write final artifacts under `output/pdf/` when working in this repo.
- Keep filenames stable and descriptive.

## Dependencies

Prefer the bundled workspace/runtime dependencies when available. The primary runtime is expected to include:

- Python packages: `reportlab`, `pdfplumber`, `pypdf`
- Rendering tools: `pdftoppm` and `pdfinfo` from Poppler

If a dependency is missing, install only what is needed.

Python packages:

```bash
uv pip install reportlab pdfplumber pypdf
```

If `uv` is unavailable:

```bash
python3 -m pip install reportlab pdfplumber pypdf
```

System tools for rendering:

```bash
# macOS (Homebrew)
brew install poppler

# Ubuntu/Debian
sudo apt-get install -y poppler-utils
```

If installation is not possible in this environment, tell the user which dependency is missing and how to install it locally.

## Environment

No required environment variables.

## Rendering Command

```bash
pdftoppm -png "$INPUT_PDF" "$OUTPUT_PREFIX"
```

## Creating PDFs

### From Text or Markdown

**Use the `create_pdf.py` script with FULL PATH**:

```bash
# From text
python d:/agent/aries/backend/plugins/skills/pdf/scripts/create_pdf.py --text "Hello World" --output hello.pdf

# From text file
python d:/agent/aries/backend/plugins/skills/pdf/scripts/create_pdf.py --input content.txt --output document.pdf

# From Markdown
python d:/agent/aries/backend/plugins/skills/pdf/scripts/create_pdf.py --input article.md --output article.pdf --format markdown

# With title
python d:/agent/aries/backend/plugins/skills/pdf/scripts/create_pdf.py --text "Content" --output doc.pdf --title "My Document"
```

**Parameters:**
- `--text, -t`: Direct text content
- `--input, -i`: Input file path (.txt, .md)
- `--output, -o`: Output PDF file path (required)
- `--title`: Document title
- `--format`: Input format (text/markdown)

## Extracting Content

### Text and Metadata

```bash
# Extract text
python d:/agent/aries/backend/plugins/skills/pdf/scripts/extract_pdf.py -i input.pdf -o output.txt

# Print metadata only
python d:/agent/aries/backend/plugins/skills/pdf/scripts/extract_pdf.py -i input.pdf --meta

# Extract tables to CSV
python d:/agent/aries/backend/plugins/skills/pdf/scripts/extract_pdf.py -i input.pdf --tables -o tables.csv
```

## Rendering Pages

```bash
# Render all pages to PNG (default)
python d:/agent/aries/backend/plugins/skills/pdf/scripts/render_pdf.py -i input.pdf -o pages/

# Render specific page range
python d:/agent/aries/backend/plugins/skills/pdf/scripts/render_pdf.py -i input.pdf -o pages/ --first 1 --last 3

# Render at higher resolution
python d:/agent/aries/backend/plugins/skills/pdf/scripts/render_pdf.py -i input.pdf -o pages/ --dpi 200
```

## Quality Expectations

- Maintain polished visual design: consistent typography, spacing, margins, and section hierarchy.
- Avoid rendering issues: clipped text, overlapping elements, broken tables, black squares, or unreadable glyphs.
- Charts, tables, and images must be sharp, aligned, and clearly labeled.
- Use ASCII hyphens only. Avoid U+2011 and other Unicode dashes.
- Citations and references must be human-readable; never leave tool tokens or placeholder strings.

## Final Checks

- Do not deliver until the latest PNG inspection shows zero visual or formatting defects.
- Confirm headers, footers, page numbering, and section transitions look polished.
- Keep intermediate files organized or remove them after final approval.
