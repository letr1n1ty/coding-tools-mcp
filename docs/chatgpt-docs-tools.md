# ChatGPT document/PDF tools

`coding-tools-mcp-chatgpt-docs` is an opt-in entrypoint for document-reading workflows in ChatGPT.
It keeps the original workspace confinement model and adds PDF context tools without loading general coding task tools.

## Install

Basic PDF extraction and rendering require PyMuPDF:

```bash
python -m pip install -e ".[pdf]"
```

Local OCR is optional. It does not call a model or external API, but it requires the `tesseract` binary on `PATH`:

```bash
brew install tesseract
```

## Start

```bash
coding-tools-mcp-chatgpt-docs --stdio --workspace /path/to/workspace
```

## Tools

- `inspect_pdf`: read PDF metadata and estimate which pages may need OCR.
- `extract_pdf_text`: extract bounded text from a PDF page range.
- `render_pdf_pages`: render bounded PDF pages as PNG data URLs for ChatGPT vision/OCR.
- `ocr_pdf_pages`: optional local Tesseract OCR for longer scanned documents.

These tools do not translate. They only provide document context to ChatGPT, so translation still
uses the host model's language ability.

## Suggested workflow

1. Call `inspect_pdf`.
2. If the PDF has a text layer, call `extract_pdf_text` in small page ranges and translate in ChatGPT.
3. If a small scanned section needs OCR, call `render_pdf_pages` and let ChatGPT inspect the page images.
4. If a long scanned PDF needs batch OCR, call `ocr_pdf_pages`, then translate the returned text in ChatGPT.

## Limits

- Paths must be workspace-relative `.pdf` files.
- The tools process bounded page ranges, not whole books in one call.
- `render_pdf_pages` returns base64 PNG data URLs and applies byte limits.
- `ocr_pdf_pages` is local-only and fails clearly if Tesseract is unavailable.
- `ocr_pdf_pages` starts a local OCR process and uses temporary files, so it is non-destructive but not marked read-only.
- No external translation, OCR, or model API is called by these tools.
