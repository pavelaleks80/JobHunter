"""
dedup.py — склейка одной и той же вакансии, опубликованной на нескольких площадках.

Дубль = та же компания (одно название начинается с другого: «МТС Банк» и «МТС Банк. Головной офис»)
и почти то же название (похожесть ≥ TITLE_SIM после удаления города и формата работы).
Основной остаётся копия с описанием (getmatch → Хабр → hh); остальные уходят в v["dups"]:
  * в отчёте у основной — «Также: hh, Хабр» со ссылками;
  * отклик на любую копию считается откликом на вакансию;
  * вакансия «новая», только если ни одна копия раньше не встречалась.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .tracker.db import STATUS_RANK, TERMINAL, norm_text

PRIORITY = {"getmatch": 0, "habr": 1, "hh": 2}
TITLE_SIM = 0.88
_NOISE = re.compile(r"\b(москва|санкт петербург|спб|удаленно|удаленка|remote|гибрид|офис|hybrid|m f|м ж)\b")


def _company(c: str) -> str:
    return norm_text(c)


def _title(t: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub(" ", norm_text(t))).strip()


def same_company(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def _better_status(a: str, b: str) -> str:
    """Статус для склеенной вакансии: любой отказ/«не интересно» важнее, иначе — самый продвинутый."""
    for st in (a, b):
        if st in TERMINAL:
            return st
    return a if STATUS_RANK.get(a, 0) >= STATUS_RANK.get(b, 0) else b


def merge(rows: list[dict]) -> tuple[list[dict], int]:
    """-> (вакансии без дублей, сколько копий склеено). Порядок — по приоритету источника и баллу."""
    ordered = sorted(rows, key=lambda v: (PRIORITY.get(v["source"], 9), -(v.get("score") or 0)))
    groups: dict[str, list[dict]] = {}          # первое слово компании → основные вакансии (для скорости)
    out, merged = [], 0
    for v in ordered:
        ck, tk = _company(v.get("company", "")), _title(v.get("title", ""))
        bucket = groups.setdefault(ck.split(" ")[0] if ck else "", [])
        main = None
        if ck:
            for m in bucket:
                if m["source"] != v["source"] and same_company(m["_ck"], ck) \
                        and SequenceMatcher(None, m["_tk"], tk).ratio() >= TITLE_SIM:
                    main = m
                    break
        if main is None:
            v = {**v, "_ck": ck, "_tk": tk, "dups": []}
            bucket.append(v)
            out.append(v)
            continue
        main["dups"].append(v)
        merged += 1
        main["is_new"] = main.get("is_new", True) and v.get("is_new", True)
        if v.get("applied"):
            main["applied"] = _better_status(main.get("applied") or "", v["applied"])
        for k in ("sal_from", "sal_to", "gross"):              # вилка с другой площадки, если у основной нет
            if main.get(k) is None and v.get(k) is not None:
                main[k] = v[k]
    for v in out:
        v.pop("_ck", None)
        v.pop("_tk", None)
    return out, merged


def also_text(v: dict, names: dict[str, str]) -> str:
    return ", ".join(names.get(d["source"], d["source"]) for d in v.get("dups") or [])
