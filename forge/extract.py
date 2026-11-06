"""Document parsing runs in a disposable subprocess with CPU and wall-clock limits."""

import json
import re
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_PAGES = 100
MAX_TEXT = 2_000_000


def extract(path: Path, suffix: str, probe: bool = False) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8-sig")
        if "\x00" in text:
            raise ValueError("The document contains binary data; upload UTF-8 text.")
        if len(text) > MAX_TEXT:
            raise ValueError("Extracted text exceeds the 2 million character limit.")
        if not text.strip():
            raise ValueError("The document is empty.")
        pages.append({"number": 1, "text": text, "ocr": False})
    elif suffix == ".pdf":
        import pymupdf

        with pymupdf.open(path) as doc:  # type: ignore[no-untyped-call]  # Vendor constructor lacks types.
            if not doc.is_pdf:
                raise ValueError("The file is not a PDF.")
            if doc.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported. Upload an unencrypted copy.")
            if not 0 < len(doc) <= MAX_PAGES:
                raise ValueError("PDFs must contain between 1 and 100 pages.")
            if probe:
                return {"pages": [], "warnings": []}
            total = 0
            for page in doc:
                text = page.get_text("text", sort=True)
                ocr = len(text.strip()) < 20
                if ocr:
                    with tempfile.TemporaryDirectory() as tmp:
                        image = Path(tmp) / "page.png"
                        scale = min(2.0, 3000 / max(page.rect.width, page.rect.height, 1))
                        matrix = pymupdf.Matrix(scale, scale)  # type: ignore[no-untyped-call]
                        page.get_pixmap(matrix=matrix).save(image)
                        try:
                            result = subprocess.run(
                                ["tesseract", str(image), "stdout", "-l", "eng"],
                                capture_output=True,
                                timeout=25,
                                check=False,
                            )
                        except FileNotFoundError as exc:
                            raise ValueError("OCR needs Tesseract installed on PATH.") from exc
                        if result.returncode:
                            raise ValueError(f"OCR failed on page {page.number + 1}.")
                        text = result.stdout.decode("utf-8")
                    warnings.append(
                        f"Page {page.number + 1}: OCR used (English); verify recognition accuracy."
                    )
                if not text.strip():
                    warnings.append(f"Page {page.number + 1}: no readable text found.")
                total += len(text)
                if total > MAX_TEXT:
                    raise ValueError("Extracted text exceeds the 2 million character limit.")
                pages.append({"number": page.number + 1, "text": text, "ocr": ocr})
    else:
        raise ValueError("Use .txt, .md, or .pdf files.")
    if not probe and not any(p["text"].strip() for p in pages):
        raise ValueError("No readable text was found.")
    return {"pages": pages, "warnings": warnings}


def chunk_text(text: str, target: int = 500, overlap: int = 75) -> list[str]:
    """Whitespace-token approximation; headings start fresh sections, pages never merge."""
    if target <= overlap or overlap < 0:
        raise ValueError("Chunk target must exceed a nonnegative overlap.")
    sections = re.split(r"(?m)(?=^#{1,6}\s)", text)
    chunks: list[str] = []
    for section in sections:
        words = section.split()
        start = 0
        while start < len(words):
            chunks.append(" ".join(words[start : start + target]))
            if start + target >= len(words):
                break
            start += target - overlap
    return chunks


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    try:
        result = extract(Path(sys.argv[1]), sys.argv[2], "--probe" in sys.argv)
    except Exception as exc:
        # Parser errors may contain file contents; return a bounded, non-sensitive message.
        message = (
            str(exc) if isinstance(exc, (ValueError, UnicodeError)) else "Document parsing failed."
        )
        print(json.dumps({"error": message[:400]}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
