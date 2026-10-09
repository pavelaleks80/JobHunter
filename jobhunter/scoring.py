"""
scoring.py — фильтр по названию и балл вакансии 0…100 с понятными причинами.

Балл = роль (до 30) + ключевые слова-усилители (до boosts_cap) + целевая компания + зарплата (до 20) + свежесть (до 10).
Каждая составляющая попадает в колонку «Почему балл».
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .config import SalaryCfg, ScoringCfg


class Scorer:
    def __init__(self, cfg: ScoringCfg, salary: SalaryCfg):
        self.cfg, self.sal = cfg, salary
        self._roles = [(re.compile(r.pattern, re.I), r.points, r.label or r.pattern) for r in cfg.roles]
        self._excl = [re.compile(p, re.I) for p in cfg.exclude]
        self._boosts = [(re.compile(b.pattern, re.I), b.points, b.label or b.pattern) for b in cfg.boosts]
        self._companies = [c.lower() for c in cfg.target_companies]
        self._black = [c.lower() for c in cfg.blacklist_companies]

    @staticmethod
    def _norm(t: str) -> str:
        return (t or "").lower().replace("ё", "е")

    WIDE_LABEL = "нестандартное название"

    def excluded(self, title: str) -> bool:
        t = self._norm(title)
        return any(x.search(t) for x in self._excl)

    def role_of(self, title: str):
        """(баллы, ярлык) или None — вакансия не наша."""
        t = self._norm(title)
        if self.excluded(title):
            return None
        best = None
        for rx, pts, lab in self._roles:
            if rx.search(t) and (best is None or pts > best[0]):
                best = (pts, lab)
        return best

    def net_salary(self, v: dict):
        """Верх вилки на руки или None. Неизвестно gross/net → считаем как gross (осторожно)."""
        top = v.get("sal_to") or v.get("sal_from")
        if not top or (v.get("currency") or "RUB") != self.sal.currency:
            return None
        return top if v.get("gross") is False else top * (1 - self.sal.tax)

    def blacklisted(self, company: str) -> bool:
        c = (company or "").lower()
        return bool(c) and any(b in c for b in self._black)

    def score(self, v: dict, today: date | None = None):
        today = today or date.today()
        if self.blacklisted(v.get("company", "")):
            return None
        role = self.role_of(v["title"])
        wide = False
        if role is None:
            # широкий поиск — только там, где есть описание для сверки (у подборок hh его нет)
            if not self.cfg.wide or v.get("source") == "hh" or self.excluded(v["title"]):
                return None
            role, wide = (self.cfg.wide_points, self.WIDE_LABEL), True
        pts, why = role[0], [f"роль: {role[1]} +{role[0]}"]

        blob = self._norm(f"{v['title']} {v['company']} {v.get('text', '')}")
        boost, tags = 0, []
        for rx, p, lab in self._boosts:
            if rx.search(blob):
                boost += p
                tags.append(lab)
        boost = min(boost, self.cfg.boosts_cap)
        if boost:
            pts += boost
            why.append(f"ключевые слова ({', '.join(tags)}) +{boost}")

        comp = (v.get("company") or "").lower()
        if comp and any(c in comp for c in self._companies):
            pts += self.cfg.target_company_bonus
            why.append(f"целевая компания +{self.cfg.target_company_bonus}")

        net = self.net_salary(v)
        k = 1000
        if net is None:
            sp, slab = self.sal.hidden_points, "вилка не указана"
        elif net >= self.sal.target:
            sp, slab = 20, f"≥ {self.sal.target // k} тыс. на руки"
        elif net >= self.sal.floor:
            sp, slab = 15, f"≥ пола {self.sal.floor // k} тыс."
        elif net >= self.sal.low:
            sp, slab = 8, f"{self.sal.low // k}–{self.sal.floor // k} тыс."
        else:
            sp, slab = 0, "НИЖЕ ПОЛА"
        pts += sp
        why.append(f"зарплата: {slab} +{sp}")

        try:
            age = (today - datetime.strptime(v["published"][:10], "%Y-%m-%d").date()).days
        except (ValueError, TypeError, KeyError):
            age = None
        fp = 0
        if age is not None:
            for days, p in self.cfg.fresh_points:
                if age <= days:
                    fp = p
                    break
        if fp:
            pts += fp
            why.append(f"свежая ({age} дн.) +{fp}")

        return {"score": min(pts, 100), "role": role[1], "tags": ", ".join(tags), "net_top": net,
                "why": "; ".join(why), "age_days": age, "wide": wide}
