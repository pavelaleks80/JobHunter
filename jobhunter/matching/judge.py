"""
judge.py — ИИ-судья: оценивает «не распознанные» правилами требования по краткому профилю кандидата.

Режим matching.mode = "hybrid": правила работают как раньше, а то, что попало в unknown, отправляется
одним запросом на вакансию в LLM. Ответы кэшируются в SQLite (одинаковые формулировки не оплачиваются дважды).
"""
from __future__ import annotations

import hashlib

SYSTEM = """Ты оцениваешь, закрывает ли опыт кандидата требования вакансии. Для каждого требования верни вердикт:
"yes" — закрыто опытом из профиля; "partial" — частично/смежный опыт; "no" — нет; "soft" — личное качество.
Ответ — JSON {"items": [{"i": <номер>, "v": "yes|partial|no|soft", "why": "<до 12 слов: чем закрыто или чего нет>"}]}."""

_SCHEMA = "CREATE TABLE IF NOT EXISTS judge_cache(key TEXT PRIMARY KEY, verdict TEXT, why TEXT)"


def _key(profile_summary: str, req: str) -> str:
    return hashlib.sha1(f"{profile_summary}\x00{req.lower().strip()}".encode()).hexdigest()


def judge(client, con, profile, reqs: list[str]) -> dict[str, tuple[str, str]]:
    """-> {требование: (вердикт, пояснение)}; что не удалось оценить — отсутствует в ответе."""
    con.execute(_SCHEMA)
    summary = profile.summary or profile.headline
    out, todo = {}, []
    for r in reqs:
        row = con.execute("SELECT verdict, why FROM judge_cache WHERE key=?", (_key(summary, r),)).fetchone()
        if row:
            out[r] = (row[0], row[1])
        else:
            todo.append(r)
    if not todo:
        return out
    skills = "; ".join(s.note for s in profile.skills[:40])
    user = (f"Кандидат: {profile.headline}. {summary}\nСтаж: {profile.years.default} лет. Английский: {profile.english}.\n"
            f"Подтверждённые навыки: {skills}\n\nТребования:\n" + "\n".join(f"{i}. {r}" for i, r in enumerate(todo, 1)))
    data = client.chat_json(SYSTEM, user)
    for it in data.get("items") or []:
        try:
            r = todo[int(it["i"]) - 1]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        v = it.get("v")
        if v not in ("yes", "partial", "no", "soft"):
            continue
        why = f"ИИ: {it.get('why', '')}".strip()
        out[r] = (v, why)
        con.execute("INSERT OR REPLACE INTO judge_cache VALUES (?,?,?)", (_key(summary, r), v, why))
    con.commit()
    return out


def apply(res: dict, verdicts: dict[str, tuple[str, str]], matcher) -> dict:
    """Перенести оценённые ИИ требования из unknown в группы и пересчитать fit/verdict."""
    if not verdicts:
        return res
    must = [x.split(" → ", 1)[0] for k in ("have", "miss", "gap", "partial") for x in res[k]] + res["unknown"]
    extra = {r: v for r, v in verdicts.items() if r in res["unknown"]}
    base = matcher.match([r for r in must if r not in extra], res.get("nice"))
    base["stop"] = res["stop"]
    pts = sum({"yes": 1, "gap": .75, "partial": .5, "no": 0}[k] * len(base[g])
              for k, g in (("yes", "have"), ("gap", "gap"), ("partial", "partial"), ("no", "miss")))
    n = base["recognized"]
    for r, (v, why) in extra.items():
        if v == "soft":
            continue
        base[{"yes": "have", "no": "miss", "partial": "partial"}[v]].append(f"{r} → {why}")
        pts += {"yes": 1, "partial": .5, "no": 0}[v]
        n += 1
    c = matcher.cfg
    fit = round(100 * pts / n) if n else None
    if n < c.min_recognized:
        verdict = "Проверь вручную"
    elif base["stop"] or len(base["hard"]) >= 2:
        verdict = "Не подходит"
    elif fit >= c.fit_ok and not base["hard"]:
        verdict = "Подходит"
    elif fit >= c.fit_partial:
        verdict = "Частично"
    else:
        verdict = "Не подходит"
    base.update(fit=fit, verdict=verdict, recognized=n, total=res["total"])
    return base
