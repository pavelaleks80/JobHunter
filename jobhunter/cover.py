"""
cover.py — сопроводительное письмо под вакансию: резюме + профиль + требования вакансии → LLM → covers/<источник>_<id>.md.

Правила для модели: только факты из резюме (ничего не придумывать), 2–3 требования вакансии подкрепить конкретикой,
без штампов. В файл кладётся черновик с шапкой (вакансия, ссылка, что закрыто/не закрыто) — его стоит перечитать
и поправить перед отправкой.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .matching import extract
from .report.common import why_only
from .tracker import db

SYSTEM = """Ты помогаешь соискателю написать сопроводительное письмо к отклику на вакансию. Пиши по-русски,
от первого лица, обращение — «Здравствуйте!».

Жёсткие правила:
- Используй ТОЛЬКО факты из резюме и профиля кандидата. Не придумывай компании, цифры, проекты, навыки.
- Начни с одной фразы, почему откликаешься именно сюда (по описанию вакансии: продукт, задача, отрасль).
- Возьми 2–3 главных требования вакансии и для каждого — конкретный факт из опыта (проект, цифра, результат).
- Если у кандидата есть пробел по важному требованию и есть смежный опыт — одной фразой честно скажи, чем он
  закрывается. Если смежного опыта нет — не упоминай.
- Без штампов: «ответственный», «коммуникабельный», «стрессоустойчивый», «быстро обучаюсь», «команда профессионалов».
- Заверши предложением созвониться или обсудить задачу. Никаких плейсхолдеров вида [Имя], [телефон].
- Верни только текст письма, без темы и без пояснений."""


def cover_path(settings, source: str, vid: str) -> Path:
    return settings.covers_dir / f"{source}_{vid}.md"


def existing(settings, source: str, vid: str) -> Path | None:
    p = cover_path(settings, source, vid)
    return p if p.exists() else None


def build_prompt(resume_text: str, profile, vac: dict, must: list[str], match: dict | None, cfg) -> str:
    lines = [f"Вакансия: {vac.get('title') or '(название не указано)'}",
             f"Компания: {vac.get('company') or '(не указана)'}"]
    if must:
        lines.append("Требования вакансии:\n" + "\n".join(f"- {r}" for r in must[:15]))
    if vac.get("_desc"):
        lines.append("Описание вакансии (фрагмент):\n" + vac["_desc"][:3000])
    if match:
        have = why_only(match.get("have", []))[:8]
        miss = why_only(match.get("miss", []) + match.get("partial", []))[:6]
        if have:
            lines.append("Что из требований закрыто опытом (по сверке): " + "; ".join(dict.fromkeys(have)))
        if miss:
            lines.append("Что не закрыто или закрыто частично: " + "; ".join(dict.fromkeys(miss)))
    lines.append(f"\nПрофиль кандидата: {profile.headline}. {profile.summary}")
    lines.append(f"\nРезюме кандидата:\n{resume_text[:12000]}")
    lines.append(f"\nДлина — около {cfg.words} слов. Тон — {cfg.tone}." + (f" {cfg.extra}" if cfg.extra else ""))
    return "\n".join(lines)


def clean_letter(text: str, signature: str = "") -> str:
    t = text.strip()
    t = re.sub(r"^```\w*\s*|\s*```$", "", t).strip()
    t = re.sub(r"^(Тема|Subject)\s*:.*\n+", "", t)
    t = re.sub(r"\[(?:Имя|Ваше имя|телефон|Телефон|контакт\w*|e-?mail)[^\]]*\]", "", t).strip()
    if signature:
        t += "\n\n" + signature.strip()
    return t


def write(settings, vac: dict, text: str, match: dict | None = None) -> Path:
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    p = cover_path(settings, vac["source"], vac["id"])
    head = [f"<!-- JobHunter · черновик сопроводительного письма · {datetime.now():%d.%m.%Y %H:%M} -->",
            f"# {vac.get('title') or 'Вакансия'} — {vac.get('company') or ''}".rstrip(" —"),
            f"{vac.get('url') or ''}", ""]
    if match and match.get("verdict"):
        head.insert(3, f"Сверка: {match['verdict']}, {match.get('fit')}%")
    p.write_text("\n".join(head) + "\n---\n\n" + text + "\n", encoding="utf-8")
    return p


def vacancy_for(con, settings, s, url: str, title: str = "", company: str = "") -> tuple[dict, dict]:
    """Вакансия и её описание: из базы, иначе — по ссылке getmatch/Хабра. -> (vac, detail)."""
    from . import sources
    v = db.find_vacancy(con, url)
    u = db.norm_url(url)
    if v is None:
        m = re.search(r"(getmatch)\.ru/vacancies/(\d+)|career\.(habr)\.com/vacancies/(\d+)|hh\.ru/vacancy/(\d+)", u)
        if not m:
            raise ValueError(f"не понимаю ссылку: {url}")
        src, vid = ("getmatch", m.group(2)) if m.group(1) else ("habr", m.group(4)) if m.group(3) else ("hh", m.group(5))
        v = {"source": src, "id": vid, "title": title, "company": company, "url": u}
    d = db.get_detail(con, v["source"], v["id"])
    if d is None and v["source"] in ("getmatch", "habr") and s is not None:
        d = sources.detail(s, settings, v["source"], v["id"])
        db.put_detail(con, v["source"], v["id"], d, datetime.now().strftime("%Y-%m-%d"))
    return v, d or {"desc": "", "english": None, "years": None}


def make(client, settings, profile, matcher, resume_text: str, vac: dict, detail: dict) -> tuple[str, dict | None]:
    """-> (текст письма, результат сверки)."""
    must, nice = extract(detail.get("desc") or "")
    match = matcher.match(must, nice, detail.get("english"), detail.get("years")) if must else None
    vac = {**vac, "_desc": re.sub(r"<[^>]+>", " ", detail.get("desc") or "")}
    vac["_desc"] = re.sub(r"\s+", " ", vac["_desc"]).strip()
    text = client.chat(SYSTEM, build_prompt(resume_text, profile, vac, must, match, settings.cover))
    return clean_letter(text, settings.cover.signature), match
