"""common.py — форматирование, общее для Excel и письма."""
from __future__ import annotations


def salary_text(v: dict) -> str:
    a, b = v.get("sal_from"), v.get("sal_to")
    if not a and not b:
        return "не указана"
    f = lambda x: f"{int(x):,}".replace(",", " ")      # noqa: E731
    s = (f(a) if a == b else f"{f(a)}–{f(b)}") if a and b else (f"от {f(a)}" if a else f"до {f(b)}")
    tax = {True: " до НДФЛ", False: " на руки"}.get(v.get("gross"), "")
    cur = "" if v.get("currency") == "RUB" else f" {v.get('currency')}"
    return s + cur + tax


def why_only(items):
    """'требование → пояснение' → 'пояснение'."""
    return [x.split(" → ", 1)[1] if " → " in x else x for x in items]
