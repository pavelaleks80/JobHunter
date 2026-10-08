"""Хабр Карьера — недокументированный фронтовый JSON + HTML страницы вакансии (обычно только без VPN)."""
from __future__ import annotations

import json
import re

from ..net import get_json
from . import vacancy

API = "https://career.habr.com/api/frontend/vacancies"
_DESC = [re.compile(r'<div class="vacancy-description__text">(.*?)</div>\s*</div>\s*</div>', re.S),
         re.compile(r'<div class="style-ugc">(.*?)</div>', re.S)]


def fetch(s, settings) -> list[dict]:
    cfg = settings.sources.habr
    out = {}
    for q in cfg.queries:
        for page in range(1, cfg.pages + 1):
            j = get_json(s, API, params={"q": q, "locations[]": cfg.location, "sort": "date", "type": "all",
                                         "currency": "RUR", "page": page}, timeout=settings.http_timeout)
            for it in j.get("list", []):
                sal = it.get("salary") or {}
                pub = it.get("publishedDate") or {}
                comp = it.get("company") or {}
                skills = " ".join(x.get("title", "") for x in it.get("skills") or [] if isinstance(x, dict))
                divs = " ".join(x.get("title", "") for x in it.get("divisions") or [] if isinstance(x, dict))
                out[it["id"]] = vacancy(
                    "habr", it["id"], it.get("title"), comp.get("title"),
                    "https://career.habr.com" + (it.get("href") or f"/vacancies/{it['id']}"),
                    (pub.get("date") or "")[:10] if isinstance(pub, dict) else "",
                    sal.get("from"), sal.get("to"),
                    {"rur": "RUB"}.get((sal.get("currency") or "rur").lower(), sal.get("currency")),
                    None,                                   # Хабр не пишет, до или после налогов
                    f"{skills} {divs} {it.get('salaryQualification') or ''}",
                    "; ".join(x.get("title", "") for x in it.get("locations") or [] if isinstance(x, dict)),
                    bool(it.get("remoteWork")),
                )
            meta = j.get("meta") or {}
            if page >= (meta.get("totalPages") or 1):
                break
    return list(out.values())


def detail(s, settings, vid) -> dict:
    r = s.get(f"https://career.habr.com/vacancies/{vid}", timeout=settings.http_timeout)
    r.raise_for_status()
    page = r.text
    for rx in _DESC:
        m = rx.search(page)
        if m and len(m.group(1)) > 200:
            return {"desc": m.group(1), "english": None, "years": None}
    m = re.search(r'"description"\s*:\s*"((?:\\.|[^"\\]){200,})"', page)
    if m:
        return {"desc": json.loads(f'"{m.group(1)}"'), "english": None, "years": None}
    raise RuntimeError("описание на странице не найдено")
