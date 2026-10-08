"""
sources — сбор вакансий. Каждый источник возвращает список словарей единого вида (см. vacancy()).

Ошибка одного источника не роняет остальные: collect() записывает её в статус и идёт дальше.
"""
from __future__ import annotations

import html
import re
from datetime import datetime

_TAG = re.compile(r"<[^>]+>")


def clean(t: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", t or ""))).strip()


def vacancy(source, vid, title, company, url, published, sal_from=None, sal_to=None, currency="RUB",
            gross=None, text="", location="", remote=None) -> dict:
    """Единый формат вакансии. gross=True — вилка до вычета налога, False — на руки, None — неизвестно."""
    return {
        "source": source, "id": str(vid), "title": (title or "").strip(), "company": (company or "").strip(),
        "url": url, "published": published or "", "sal_from": sal_from, "sal_to": sal_to,
        "currency": currency or "RUB", "gross": gross, "text": text, "location": location, "remote": remote,
    }


def collect(s, settings):
    """Опросить включённые сайты. -> (вакансии, {источник: (ok, текст)})."""
    from . import getmatch, habr
    plan = []
    if settings.sources.getmatch.enabled:
        plan.append(("getmatch", lambda: getmatch.fetch(s, settings)))
    if settings.sources.habr.enabled:
        plan.append(("habr", lambda: habr.fetch(s, settings)))
    allv, status = [], {}
    for name, fn in plan:
        t0 = datetime.now()
        try:
            v = fn()
            allv += v
            status[name] = (True, f"{len(v)} вакансий за {(datetime.now() - t0).seconds} с")
        except Exception as e:      # noqa: BLE001
            msg = str(e)
            if name == "habr" and ("timed out" in msg or "Max retries" in msg):
                msg = "не отвечает (Хабр Карьера обычно недоступна через VPN)"
            status[name] = (False, msg[:300])
    return allv, status


def detail(s, settings, source: str, vid: str) -> dict:
    """Полное описание вакансии: {"desc": html, "english": ..., "years": ...}."""
    from . import getmatch, habr
    return {"getmatch": getmatch.detail, "habr": habr.detail}[source](s, settings, vid)
