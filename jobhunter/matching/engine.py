"""
engine.py — сверка требований с профилем по правилам из profile.yaml.

Matcher.match(must, nice, english_level, years_required) -> dict:
  fit     — доля закрытых обязательных требований 0..100 (yes = 1, gap = 0.75, partial = 0.5, no = 0);
  verdict — «Подходит» (fit ≥ fit_ok, нет стоп-факторов и критичных пробелов) / «Частично» (fit ≥ fit_partial,
            не больше 1 критичного пробела) / «Не подходит» / «Проверь вручную» (распознано < min_recognized);
  hard    — критичные пробелы (missing с hard: true);
  stop    — стоп-факторы (английский выше уровня кандидата, нехватка стажа);
  have/miss/gap/partial/unknown — требования по группам для отчёта.
"""
from __future__ import annotations

import re

from ..config import MatchingCfg
from ..profile.schema import LEVELS, Profile

_PRIO = {"no": 4, "partial": 3, "gap": 2, "yes": 1, "soft": 0}
_WEIGHT = {"yes": 1.0, "gap": 0.75, "partial": 0.5, "no": 0.0}
_YEARS_RE = re.compile(r"(?:от|не менее|минимум|более|больше)\s*(\d{1,2})(?:[-–]?х)?\s*(?:\+\s*)?(?:лет|год)|"
                       r"(\d{1,2})\+?\s*(?:years|лет|год)", re.I)
_NUM_WORDS = {"одного": "1", "двух": "2", "трех": "3", "четырех": "4", "пяти": "5", "шести": "6",
              "семи": "7", "восьми": "8", "десяти": "10"}
_OR = re.compile(r"\sили\s|\sor\s|/")
_ENGLISH = re.compile(r"английск|english|upper|intermediate|\b[abc][12]\b|иностранн\w* язык", re.I)
_EDU = re.compile(r"(?<![а-я])(образовани|высше[ем]\w*\s+образ|высшее(?![а-я]))")
_LEVEL_RE = re.compile(r"\b([abc][12])\b|(upper[- ]?intermediate)|(intermediate)|(advanced|fluent)", re.I)

# Универсальные «личные качества» — в процент не входят (для любого профиля)
SOFT = (r"фасилитац|конфликт|деловую переписку|аргументир|организованност|коммуникаци|коммуницир|коммуникаб|"
        r"коммуникатив|самостоятельн|ответственн|неопределенн|стрессоустойч|аналитическ\w* (мышлен|склад|способн)|"
        r"системн\w* мышлен|инициатив|проактивн|ownership|лидерств|гибкост|адаптивн|креатив|внимательн|"
        r"самоорганизац|договариваться|грамотн\w* (устн|речь)|излагать|простым языком|желание|готовност|"
        r"замотивирован|страсть|ориентаци\w* на результат|soft skills|офис|гибридн|5/2|командировк|"
        r"решать проблем|проблемные места|с разных сторон|разных источник|широко мысл|менеджерск\w* навык")


def _norm(t: str) -> str:
    t = (t or "").lower().replace("ё", "е")
    return re.sub(r"\b(одного|двух|трех|четырех|пяти|шести|семи|восьми|десяти)(-х)?(?=\s+(лет|год))",
                  lambda m: _NUM_WORDS[m.group(1)], t)


def _required_level(t: str) -> int | None:
    m = _LEVEL_RE.search(t)
    if not m:
        return None
    if m.group(1):
        return LEVELS.index(m.group(1).upper())
    if m.group(2):
        return LEVELS.index("B2")
    if m.group(3):
        return LEVELS.index("B1")
    return LEVELS.index("C1")


class Matcher:
    def __init__(self, profile: Profile, cfg: MatchingCfg | None = None):
        self.p, self.cfg = profile, cfg or MatchingCfg()
        rules = []
        for verdict, group in (("no", profile.missing), ("partial", profile.partial),
                               ("gap", profile.hidden), ("yes", profile.skills)):
            for r in group:
                rules.append((re.compile(r.match, re.I), verdict, r.note or r.match, r.hard))
        rules.append((re.compile(SOFT, re.I), "soft", "личное качество", False))
        self._rules = rules
        self._hard = {note for _, v, note, hard in rules if v == "no" and hard}
        self._areas = [(re.compile(a.match, re.I), a.years) for a in profile.years.areas]
        self._edu = re.compile(profile.education.match, re.I) if profile.education.match else None

    @property
    def hard_notes(self) -> set[str]:
        return self._hard

    def _years_cap(self, t: str) -> int:
        for rx, y in self._areas:
            if rx.search(t):
                return y
        return self.p.years.default

    def classify(self, req: str):
        """-> (вердикт, пояснение) или (None, None)."""
        t = _norm(req)
        # английский — по уровню профиля, а не по правилам
        if _ENGLISH.search(t):
            need = _required_level(t)
            have = self.p.english_rank()
            if need is None:
                need = LEVELS.index("B1")
            if have >= need:
                return "yes", f"английский {self.p.english}"
            return "no", f"английский — {self.p.english}"
        # образование — только по полю education
        if _EDU.search(t):                       # «ценообразование» — не про образование
            e = self.p.education
            if not e.level:
                return "partial", "образование не указано в профиле"
            if self._edu and self._edu.search(t):
                return "yes", f"{e.level} {e.field}".strip()
            if re.search(r"информ|математ|экономич|финанс|техническ|юридич|computer science|профильн", t):
                return "partial", f"{e.level} {e.field} — не то направление".strip()
            return "yes", f"{e.level} {e.field}".strip()

        found = [(v, note) for rx, v, note, _ in self._rules if rx.search(t)]
        best = max(found, key=lambda x: _PRIO[x[0]]) if found else None
        # «X или Y»: альтернатива после проваленной части закрыта → частично
        if best and best[0] == "no" and _OR.search(t):
            parts = _OR.split(t)
            verdicts = [{v for rx, v, _, _ in self._rules if rx.search(p)} for p in parts]
            first_no = next((i for i, vs in enumerate(verdicts) if "no" in vs), len(parts))
            for vs in verdicts[first_no + 1:]:
                if "yes" in vs and "no" not in vs:
                    best = ("partial", best[1] + " (но альтернатива в требовании закрыта)")
                    break
        # «опыт от N лет»
        m = _YEARS_RE.search(t)
        if m and best and best[0] in ("yes", "partial", "gap"):
            n = int(m.group(1) or m.group(2))
            cap = self._years_cap(t)
            if n > cap:
                best = ("no", f"нужно от {n} лет, у кандидата ~{cap}")
        return best or (None, None)

    def match(self, must, nice=None, english_level=None, years_required=None) -> dict:
        res = {"have": [], "miss": [], "gap": [], "partial": [], "unknown": [], "stop": [], "hard": []}
        pts = n = 0
        for req in must:
            v, why = self.classify(req)
            if v is None:
                res["unknown"].append(req)
                continue
            if v == "soft":
                continue
            n += 1
            pts += _WEIGHT[v]
            res[{"yes": "have", "no": "miss", "gap": "gap", "partial": "partial"}[v]].append(f"{req} → {why}")
            if v == "no" and why in self._hard:
                res["hard"].append(why)
            if v == "no" and why.startswith("английский"):
                res["stop"].append("обязательный английский")
        if english_level:
            lvl = english_level.get("name", "") if isinstance(english_level, dict) else str(english_level)
            m = re.search(r"\b([ABC][12])\b", lvl)
            if m and LEVELS.index(m.group(1)) > self.p.english_rank():
                res["stop"].append(f"английский {m.group(1)} (в карточке)")
        if years_required and years_required > self.p.years.default:
            res["stop"].append(f"стаж от {years_required} лет")
        res["stop"] = sorted(set(res["stop"]))

        fit = round(100 * pts / n) if n else None
        c = self.cfg
        if n < c.min_recognized:
            verdict = "Проверь вручную"
        elif res["stop"] or len(res["hard"]) >= 2:
            verdict = "Не подходит"
        elif fit >= c.fit_ok and not res["hard"]:
            verdict = "Подходит"
        elif fit >= c.fit_partial:
            verdict = "Частично"
        else:
            verdict = "Не подходит"
        res.update(fit=fit, verdict=verdict, recognized=n, total=len(must), nice=list(nice or []))
        return res

    def match_title(self, title: str) -> dict:
        """Вакансии без описания (подборки hh из почты): только критичный пробел в самом названии."""
        r = self.match([])
        v, why = self.classify(title)
        if v == "no" and why in self._hard:
            r.update(verdict="Не подходит", hard=[why], miss=[f"{title} → {why} (по названию)"])
        return r
