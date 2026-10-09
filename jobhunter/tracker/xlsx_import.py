"""
xlsx_import.py — отклики из вашего собственного Excel-трекера (только чтение).

Многие ведут отклики в своей таблице. JobHunter читает её при каждом запуске и переносит в воронку, чтобы вакансии,
на которые вы уже откликнулись, не приходили в письме. Таблица не изменяется.

  * Файл можно держать открытым в Excel: читается его копия в памяти. Но видно только **сохранённое** —
    после правки нажмите Ctrl+S.
  * Колонки задаются буквами в config.yaml (секция tracker_import), первая строка данных — first_row;
    для viewed / invited можно перечислить несколько через запятую: «H,I».
  * Статус: «Откликнулся» по умолчанию; непустые колонки viewed / invited — «Ответили» / «Приглашение»;
    текст колонки result проверяется регулярками rejected / ignored / offer.
  * Повторный импорт ничего не дублирует (события уникальны по вакансии, статусу и источнику).
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string

from . import db

_SITES = {"hh.ru": "hh", "getmatch.ru": "getmatch", "career.habr.com": "habr"}


def _col(letter: str | None) -> int | None:
    return column_index_from_string(letter.strip().upper()) - 1 if letter else None


def _cols(letters: str | None) -> list[int]:
    """«H» или «H,I» → индексы колонок."""
    return [_col(x) for x in (letters or "").split(",") if x.strip()]


def _first(row, idxs):
    """Первое непустое значение из нескольких колонок (или None)."""
    return next((v for v in (_cell(row, i) for i in idxs) if v not in (None, "")), None)


def _cell(row, idx):
    return row[idx] if idx is not None and idx < len(row) else None


def _day(v) -> str | None:
    """Дата из ячейки: datetime/date или строка «08.10.2026» / «2026-10-08». Иначе None."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    s = str(v or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _source(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    host = m.group(1).lower() if m else ""
    return next((v for k, v in _SITES.items() if host.endswith(k)), host or "")


def read_rows(cfg) -> list[dict]:
    """Строки трекера → [{url, title, company, applied, statuses: [(status, день|None)]}]."""
    path = Path(cfg.path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"трекер не найден: {path}")
    data = io.BytesIO(path.read_bytes())           # копия в памяти: файл может быть открыт в Excel
    wb = openpyxl.load_workbook(data, read_only=True, data_only=True)
    if cfg.sheet not in wb.sheetnames:
        raise ValueError(f"в трекере нет листа «{cfg.sheet}» (есть: {', '.join(wb.sheetnames)})")
    c = cfg.columns
    ix = {k: _col(getattr(c, k)) for k in ("title", "url", "company", "date", "result")}
    multi = {k: _cols(getattr(c, k)) for k in ("viewed", "invited")}
    rx = {k: re.compile(getattr(cfg, k), re.I) for k in ("rejected", "ignored", "offer") if getattr(cfg, k)}
    out = []
    for n, row in enumerate(wb[cfg.sheet].iter_rows(values_only=True), 1):
        if n < cfg.first_row:
            continue
        url = str(_cell(row, ix["url"]) or "").strip()
        title = str(_cell(row, ix["title"]) or "").strip()
        if not (url or title):
            continue
        company = str(_cell(row, ix["company"]) or "").strip()
        applied = _day(_cell(row, ix["date"]))
        statuses = []
        for status in ("viewed", "invited"):
            v = _first(row, multi[status])
            if v is not None:
                statuses.append((status, _day(v)))
        res = str(_cell(row, ix["result"]) or "").strip()
        if res:
            for status in ("offer", "rejected", "ignored"):
                if status in rx and rx[status].search(res):
                    statuses.append((status, None))
                    break
        out.append({"url": url if url.startswith("http") else "", "title": title, "company": company,
                    "applied": applied, "statuses": statuses})
    wb.close()
    return out


def import_tracker(con, cfg) -> tuple[int, int]:
    """Перенести трекер в воронку. -> (строк в трекере, изменений в базе)."""
    rows = read_rows(cfg)
    origin = f"xlsx:{Path(cfg.path).name}"
    changed = 0
    for r in rows:
        at = f"{r['applied']} 00:00" if r["applied"] else None
        src = _source(r["url"])
        changed += db.set_status(con, r["url"], r["title"], r["company"], "applied", origin, at=at, source=src)
        last = at
        for status, day in r["statuses"]:
            # дата смены статуса в трекере обычно не записана — берём последнюю известную (отказ не раньше просмотра);
            # если известна только дата отклика, в медиану времени ответа такая вакансия не попадёт
            when = f"{day} 00:00" if day else last
            last = when
            changed += db.set_status(con, r["url"], r["title"], r["company"], status, origin, at=when, source=src)
    return len(rows), changed
