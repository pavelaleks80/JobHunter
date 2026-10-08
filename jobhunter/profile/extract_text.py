"""
extract_text.py — текст резюме из workspace/resume/*.pdf | *.docx | *.txt | *.md.

PDF — pypdf (текстовый слой; сканы без OCR не читаются), DOCX — распаковка word/document.xml без сторонних
библиотек, TXT/MD — как есть. Если файлов несколько, берётся самый свежий.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SUPPORTED = (".pdf", ".docx", ".txt", ".md")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def find_resume(resume_dir: Path) -> Path:
    files = [f for f in resume_dir.iterdir() if f.suffix.lower() in SUPPORTED and not f.name.startswith("~$")] \
        if resume_dir.exists() else []
    if not files:
        raise FileNotFoundError(f"положите резюме ({', '.join(SUPPORTED)}) в {resume_dir}")
    return max(files, key=lambda f: f.stat().st_mtime)


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    lines = []
    for p in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in p.iter(f"{_W}t"))
        if text.strip():
            lines.append(text)
    return "\n".join(lines)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract(path: Path) -> str:
    ext = path.suffix.lower()
    text = {".pdf": read_pdf, ".docx": read_docx}.get(ext, read_text)(path)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) < 300:
        raise ValueError(f"из {path.name} извлечено только {len(text)} символов — похоже, это скан или пустой файл; "
                         f"сохраните резюме как DOCX/TXT")
    return text
