"""getmatch.ru — публичный JSON /api/offers (работает и с VPN, и без)."""
from __future__ import annotations

import json

from ..net import get_json
from . import clean, vacancy

API = "https://getmatch.ru/api/offers"


def _maybe_json(v):
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def fetch(s, settings) -> list[dict]:
    out = {}
    for q in settings.sources.getmatch.queries:
        params = [tuple(p) for p in q]
        offset = 0
        while True:
            j = get_json(s, API, params=params + [("limit", 100), ("offset", offset)], timeout=settings.http_timeout)
            for o in j.get("offers", []):
                if not o.get("is_active", True):
                    continue
                comp = _maybe_json(o.get("company")) or {}
                skills = _maybe_json(o.get("skills_objects")) or []
                locs = _maybe_json(o.get("location_items")) or []
                taxes = o.get("salary_taxes")
                out[o["id"]] = vacancy(
                    "getmatch", o["id"], o.get("position"), comp.get("name") if isinstance(comp, dict) else "",
                    "https://getmatch.ru" + (o.get("url") or f"/vacancies/{o['id']}"),
                    (o.get("published_at") or "")[:10],
                    None if o.get("salary_hidden") else o.get("salary_display_from"),
                    None if o.get("salary_hidden") else o.get("salary_display_to"),
                    o.get("salary_currency"), {"gross": True, "net": False}.get(taxes),
                    clean(o.get("offer_description")) + " " + " ".join(x.get("name", "") for x in skills if isinstance(x, dict)),
                    "; ".join(x.get("label", "") for x in locs if isinstance(x, dict)),
                    any(isinstance(x, dict) and x.get("format") == "remote" for x in locs),
                )
            meta = j.get("meta", {})
            offset += meta.get("limit", 100)
            if offset >= meta.get("total", 0) or not j.get("offers"):
                break
    return list(out.values())


def detail(s, settings, vid) -> dict:
    j = get_json(s, f"{API}/{vid}", timeout=settings.http_timeout)
    return {"desc": j.get("description") or j.get("description_html") or j.get("offer_description") or "",
            "english": j.get("english_level"), "years": j.get("required_years_of_experience")}
