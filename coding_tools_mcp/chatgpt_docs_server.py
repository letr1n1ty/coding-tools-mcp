from __future__ import annotations

import base64
import importlib
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable

from . import server as _server

_ORIGINAL_INPUT_SCHEMAS: Callable[[], dict[str, dict[str, Any]]] | None = None
_PATCHED = False
PDF_TOOL_NAMES = ("inspect_pdf", "extract_pdf_text", "render_pdf_pages", "ocr_pdf_pages")
LANGUAGE_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")


def _require_pymupdf() -> Any:
    try:
        return importlib.import_module("fitz")
    except ImportError as exc:
        raise _server.ToolFailure(
            "DEPENDENCY_MISSING",
            "PDF tools require PyMuPDF. Install with `pip install 'coding-tools-mcp[pdf]'`.",
            category="configuration",
            details={"missing": "PyMuPDF", "extra": "pdf"},
        ) from exc


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _open_pdf(runtime: _server.Runtime, path_arg: Any) -> tuple[Any, Any, Any]:
    fitz = _require_pymupdf()
    resolved = runtime.resolve_existing(str(path_arg or ""))
    if resolved.path.is_dir():
        raise _server.ToolFailure("IS_DIRECTORY", "Path is a directory.", category="validation")
    if resolved.path.suffix.lower() != ".pdf":
        raise _server.ToolFailure("UNSUPPORTED_FILE", "Only .pdf files are supported.", category="validation")
    try:
        doc = fitz.open(resolved.path)
    except Exception as exc:  # noqa: BLE001
        raise _server.ToolFailure(
            "PDF_OPEN_FAILED",
            "PDF could not be opened.",
            category="runtime",
            details={"reason": str(exc)[:500]},
        ) from exc
    if getattr(doc, "is_encrypted", False):
        doc.close()
        raise _server.ToolFailure("PDF_ENCRYPTED", "Encrypted PDFs are not supported.", category="validation")
    if int(doc.page_count) <= 0:
        doc.close()
        raise _server.ToolFailure("EMPTY_PDF", "PDF has no pages.", category="validation")
    return fitz, resolved, doc


def _page_numbers(doc: Any, args: dict[str, Any], *, default_limit: int, maximum: int) -> list[int]:
    count = int(doc.page_count)
    raw_pages = args.get("pages")
    if isinstance(raw_pages, list) and raw_pages:
        pages = []
        for item in raw_pages:
            page = int(item)
            if page < 1 or page > count:
                raise _server.ToolFailure(
                    "PAGE_OUT_OF_RANGE",
                    "Page number is outside the PDF page range.",
                    category="validation",
                    details={"page": page, "page_count": count},
                )
            if page not in pages:
                pages.append(page)
        if len(pages) > maximum:
            raise _server.ToolFailure("TOO_MANY_PAGES", f"At most {maximum} pages can be processed.")
        return pages
    start = _bounded_int(args.get("start_page"), 1, 1, count)
    end = _bounded_int(args.get("end_page"), min(count, start + default_limit - 1), start, count)
    return list(range(start, min(end, start + maximum - 1) + 1))


def _page_text(page: Any) -> str:
    try:
        return str(page.get_text("text") or "")
    except Exception:
        return ""


def _image_count(page: Any) -> int:
    try:
        return len(page.get_images(full=True))
    except Exception:
        return 0


def _needs_ocr(text: str, image_count: int, threshold: int) -> bool:
    return len(text.strip()) < threshold and image_count > 0


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: max(1, limit)], True


def _matrix(fitz: Any, page: Any, dpi: int, max_width: int, max_height: int) -> Any:
    scale = max(0.5, min(dpi / 72.0, 4.0))
    width = float(page.rect.width) * scale
    height = float(page.rect.height) * scale
    if width > max_width:
        scale *= max_width / width
        height = float(page.rect.height) * scale
    if height > max_height:
        scale *= max_height / height
    return fitz.Matrix(scale, scale)


def _render_png(fitz: Any, page: Any, dpi: int, max_width: int, max_height: int) -> tuple[bytes, Any]:
    matrix = _matrix(fitz, page, dpi, max_width, max_height)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    return bytes(pixmap.tobytes("png")), matrix


def inspect_pdf(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    _fitz, resolved, doc = _open_pdf(runtime, args.get("path"))
    try:
        threshold = _bounded_int(args.get("ocr_threshold_chars"), 40, 0, 2000)
        pages = []
        for number in _page_numbers(doc, args, default_limit=10, maximum=10):
            page = doc.load_page(number - 1)
            text = _page_text(page)
            images = _image_count(page)
            pages.append(
                {
                    "page": number,
                    "text_chars": len(text),
                    "text_chars_stripped": len(text.strip()),
                    "image_count": images,
                    "needs_ocr": _needs_ocr(text, images, threshold),
                }
            )
        needs_ocr_count = sum(1 for item in pages if item["needs_ocr"])
        return {
            "path": resolved.display,
            "page_count": int(doc.page_count),
            "metadata": dict(doc.metadata or {}),
            "sampled_pages": pages,
            "sample_needs_ocr_pages": needs_ocr_count,
            "likely_scanned": needs_ocr_count >= max(1, len(pages) // 2),
            "warnings": [],
        }
    finally:
        doc.close()


def extract_pdf_text(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    _fitz, resolved, doc = _open_pdf(runtime, args.get("path"))
    try:
        threshold = _bounded_int(args.get("ocr_threshold_chars"), 40, 0, 2000)
        max_chars = _bounded_int(args.get("max_chars_per_page"), 20000, 1, 100000)
        page_payloads = []
        warnings = []
        for number in _page_numbers(doc, args, default_limit=5, maximum=10):
            page = doc.load_page(number - 1)
            raw_text = _page_text(page)
            text, truncated = _truncate(raw_text, max_chars)
            images = _image_count(page)
            if truncated:
                warnings.append(f"page {number} text truncated")
            page_payloads.append(
                {
                    "page": number,
                    "text": text,
                    "text_chars": len(raw_text),
                    "output_chars": len(text),
                    "truncated": truncated,
                    "image_count": images,
                    "needs_ocr": _needs_ocr(raw_text, images, threshold),
                }
            )
        return {
            "path": resolved.display,
            "page_count": int(doc.page_count),
            "pages": page_payloads,
            "warnings": warnings,
        }
    finally:
        doc.close()


def render_pdf_pages(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    fitz, resolved, doc = _open_pdf(runtime, args.get("path"))
    try:
        dpi = _bounded_int(args.get("dpi"), 180, 72, 288)
        max_width = _bounded_int(args.get("max_width"), 1600, 256, 3000)
        max_height = _bounded_int(args.get("max_height"), 2200, 256, 4000)
        max_page_bytes = _bounded_int(args.get("max_page_bytes"), 2 * 1024 * 1024, 1, 5 * 1024 * 1024)
        total = 0
        pages = []
        for number in _page_numbers(doc, args, default_limit=1, maximum=10):
            page = doc.load_page(number - 1)
            data, matrix = _render_png(fitz, page, dpi, max_width, max_height)
            if len(data) > max_page_bytes:
                raise _server.ToolFailure("OUTPUT_TOO_LARGE", "Rendered page exceeds max_page_bytes.")
            total += len(data)
            if total > 8 * 1024 * 1024:
                raise _server.ToolFailure("OUTPUT_TOO_LARGE", "Rendered pages exceed total byte limit.")
            encoded = base64.b64encode(data).decode("ascii")
            pages.append(
                {
                    "page": number,
                    "mime_type": "image/png",
                    "bytes": len(data),
                    "width": int(round(page.rect.width * matrix.a)),
                    "height": int(round(page.rect.height * matrix.d)),
                    "base64": encoded,
                    "data_url": f"data:image/png;base64,{encoded}",
                }
            )
        return {"path": resolved.display, "page_count": int(doc.page_count), "dpi": dpi, "pages": pages, "warnings": []}
    finally:
        doc.close()


def ocr_pdf_pages(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise _server.ToolFailure("DEPENDENCY_MISSING", "Local OCR requires the `tesseract` binary on PATH.")
    language = str(args.get("language") or "eng")
    if not LANGUAGE_RE.match(language):
        raise _server.ToolFailure("INVALID_ARGUMENT", "OCR language contains unsupported characters.")
    fitz, resolved, doc = _open_pdf(runtime, args.get("path"))
    try:
        dpi = _bounded_int(args.get("dpi"), 220, 100, 300)
        timeout = _bounded_int(args.get("timeout_ms"), 120000, 1, 600000) / 1000.0
        max_chars = _bounded_int(args.get("max_chars_per_page"), 30000, 1, 100000)
        psm = _bounded_int(args.get("psm"), 1, 0, 13)
        page_payloads = []
        warnings = []
        for number in _page_numbers(doc, args, default_limit=3, maximum=10):
            data, _matrix_obj = _render_png(fitz, doc.load_page(number - 1), dpi, 2200, 3000)
            with tempfile.NamedTemporaryFile(suffix=".png") as handle:
                handle.write(data)
                handle.flush()
                completed = subprocess.run(
                    [tesseract, handle.name, "stdout", "-l", language, "--psm", str(psm)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                )
            if completed.returncode != 0:
                raise _server.ToolFailure(
                    "OCR_FAILED",
                    "Local OCR command failed.",
                    category="runtime",
                    details={"page": number, "stderr": completed.stderr[:1000]},
                )
            text, truncated = _truncate(completed.stdout, max_chars)
            if truncated:
                warnings.append(f"page {number} OCR text truncated")
            page_payloads.append(
                {"page": number, "text": text, "truncated": truncated, "stderr": completed.stderr[:1000]}
            )
        return {
            "path": resolved.display,
            "page_count": int(doc.page_count),
            "pages": page_payloads,
            "warnings": warnings,
        }
    finally:
        doc.close()


def _common_page_schema() -> dict[str, Any]:
    return {
        "path": {"type": "string"},
        "start_page": {"type": "integer", "minimum": 1, "default": 1},
        "end_page": {"type": "integer", "minimum": 1},
        "pages": {"type": "array", "items": {"type": "integer", "minimum": 1}},
    }


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": ["path"], "additionalProperties": False}


def _input_schemas_with_pdf_tools() -> dict[str, dict[str, Any]]:
    assert _ORIGINAL_INPUT_SCHEMAS is not None
    schemas = _ORIGINAL_INPUT_SCHEMAS()
    schemas["inspect_pdf"] = _schema(
        {**_common_page_schema(), "ocr_threshold_chars": {"type": "integer", "default": 40}}
    )
    schemas["extract_pdf_text"] = _schema(
        {
            **_common_page_schema(),
            "ocr_threshold_chars": {"type": "integer", "default": 40},
            "max_chars_per_page": {"type": "integer", "default": 20000},
        }
    )
    schemas["render_pdf_pages"] = _schema(
        {
            **_common_page_schema(),
            "dpi": {"type": "integer", "default": 180},
            "max_width": {"type": "integer", "default": 1600},
            "max_height": {"type": "integer", "default": 2200},
            "max_page_bytes": {"type": "integer", "default": 2097152},
        }
    )
    schemas["ocr_pdf_pages"] = _schema(
        {
            **_common_page_schema(),
            "language": {"type": "string", "default": "eng"},
            "psm": {"type": "integer", "default": 1},
            "dpi": {"type": "integer", "default": 220},
            "timeout_ms": {"type": "integer", "default": 120000},
            "max_chars_per_page": {"type": "integer", "default": 30000},
        }
    )
    return schemas


def install_pdf_tools() -> None:
    global _ORIGINAL_INPUT_SCHEMAS, _PATCHED
    if _PATCHED:
        return
    _ORIGINAL_INPUT_SCHEMAS = _server.input_schemas
    _server.input_schemas = _input_schemas_with_pdf_tools
    specs = {
        "inspect_pdf": _server.ToolSpec(
            "Inspect PDF", "Inspect a workspace PDF and estimate OCR need.", True, False, True, False, True
        ),
        "extract_pdf_text": _server.ToolSpec(
            "Extract PDF text", "Extract bounded text from a workspace PDF.", True, False, True, False, True
        ),
        "render_pdf_pages": _server.ToolSpec(
            "Render PDF pages", "Render bounded PDF pages as PNG images.", True, False, True, False, True
        ),
        "ocr_pdf_pages": _server.ToolSpec(
            "OCR PDF pages locally",
            "Run local Tesseract OCR on bounded PDF pages.",
            False,
            False,
            False,
            False,
            False,
        ),
    }
    _server.TOOL_REGISTRY.update(specs)
    for name in PDF_TOOL_NAMES:
        setattr(_server.Runtime, name, globals()[name])
    _server.FULL_TOOL_NAMES = tuple(_server.TOOL_REGISTRY)
    _server.READ_ONLY_TOOL_NAMES = tuple(
        name for name, spec in _server.TOOL_REGISTRY.items() if spec.in_read_only_profile
    )
    _PATCHED = True


def main() -> int:
    install_pdf_tools()
    return _server.main()


if __name__ == "__main__":
    raise SystemExit(main())
