"""
db.py — SQLite workspace/data/jobs.db: увиденные вакансии, кэш описаний и воронка откликов.

Воронка: таблица applications (одна строка на вакансию) со статусом
  applied   — откликнулся;
  viewed    — работодатель ответил/посмотрел (автоответ «рассмотрим», сообщение в чате);
  invited   — приглашение / работодатель написал по вакансии;
  rejected  — отказ;
  offer     — оффер;
  ignored   — «не интересно» (не показывать в отчёте).
Статус только «растёт» (applied → viewed → invited → offer); rejected и ignored ставятся всегда.
Каждое изменение пишется в events — из них считается статистика.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies(
  source TEXT, id TEXT, title TEXT, company TEXT, url TEXT, published TEXT,
  sal_from REAL, sal_to REAL, currency TEXT, gross INTEGER,
  score INTEGER, why TEXT, verdict TEXT, fit INTEGER, first_seen TEXT, last_seen TEXT,
  PRIMARY KEY(source, id));
CREATE TABLE IF NOT EXISTS details(
  source TEXT, id TEXT, descr TEXT, english TEXT, years INTEGER, fetched TEXT,
  PRIMARY KEY(source, id));
CREATE TABLE IF NOT EXISTS applications(
  key TEXT PRIMARY KEY,            -- нормализованная ссылка (или «company|title», если ссылки нет)
  url TEXT, title TEXT, company TEXT, source TEXT,
  status TEXT, applied_at TEXT, updated_at TEXT, note TEXT, origin TEXT);
CREATE TABLE IF NOT EXISTS events(
  key TEXT, at TEXT, status TEXT, origin TEXT, detail TEXT,
  UNIQUE(key, status, origin));
"""

STATUS_RANK = {"applied": 1, "viewed": 2, "invited": 3, "offer": 4}
TERMINAL = {"rejected", "ignored"}
STATUS_RU = {"applied": "Откликнулся", "viewed": "Ответили", "invited": "Приглашение", "offer": "Оффер",
             "rejected": "Отказ", "ignored": "Не интересно"}


# Колонки, добавленные после 0.1.0: роль, верх вилки на руки (для аналитики зарплат), ссылка на «основную» копию дубля
_MIGRATIONS = {"vacancies": [("role", "TEXT"), ("net_top", "REAL"), ("dup_of", "TEXT")]}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for table, cols in _MIGRATIONS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols:
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    con.commit()
    return con


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- ключи
_URL_ID = [(re.compile(r"hh\.ru/vacancy/(\d+)"), "https://hh.ru/vacancy/{}"),
           (re.compile(r"career\.habr\.com/vacancies/(\d+)"), "https://career.habr.com/vacancies/{}"),
           (re.compile(r"getmatch\.ru/vacancies/(\d+)"), "https://getmatch.ru/vacancies/{}")]


def norm_url(url: str | None) -> str:
    """Каноническая ссылка: без параметров (в т.ч. персональных ключей входа), id вакансии для известных сайтов."""
    if not url:
        return ""
    for rx, fmt in _URL_ID:
        m = rx.search(url)
        if m:
            return fmt.format(m.group(1))
    return url.split("?")[0].split("#")[0].rstrip("/")


def norm_text(s: str | None) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\b(пао|ао|ооо|зао|оао|группа|компания|банк|ltd|llc)\b", " ", s)
    return re.sub(r"[^\w]+", " ", s).strip()


def app_key(url: str | None, title: str = "", company: str = "") -> str:
    u = norm_url(url)
    return u or f"{norm_text(company)}|{norm_text(title)}"


# ---------------------------------------------------------------- вакансии
_VAC_COLS = ("source", "id", "title", "company", "url", "published", "sal_from", "sal_to", "currency", "gross",
             "score", "why", "verdict", "fit", "first_seen", "last_seen", "role", "net_top", "dup_of")


def upsert_vacancies(con, rows, run_date: str) -> set:
    """Сохранить вакансии (и их дубли с других площадок, v["dups"]). -> ключи (source, id), увиденные впервые."""
    known = {(s, i) for s, i in con.execute("SELECT source, id FROM vacancies")}
    new = set()

    def one(r, dup_of=None):
        key = (r["source"], r["id"])
        m = r.get("match") or {}
        if key not in known:
            new.add(key)
            known.add(key)
            vals = (r["source"], r["id"], r["title"], r["company"], r["url"], r["published"], r["sal_from"],
                    r["sal_to"], r["currency"], None if r["gross"] is None else int(r["gross"]), r.get("score"),
                    r.get("why"), m.get("verdict"), m.get("fit"), run_date, run_date, r.get("role"),
                    r.get("net_top"), dup_of)
            con.execute(f"INSERT INTO vacancies ({', '.join(_VAC_COLS)}) VALUES ({', '.join('?' * len(_VAC_COLS))})", vals)
        else:
            con.execute("UPDATE vacancies SET last_seen=?, score=?, why=?, verdict=?, fit=?, role=?, net_top=?, dup_of=? "
                        "WHERE source=? AND id=?", (run_date, r.get("score"), r.get("why"), m.get("verdict"),
                                                    m.get("fit"), r.get("role"), r.get("net_top"), dup_of, *key))

    for r in rows:
        one(r)
        for d in r.get("dups") or []:
            one(d, f"{r['source']}:{r['id']}")
    con.commit()
    return new


def find_vacancy(con, url: str) -> dict | None:
    """Вакансия из базы по ссылке (с любыми параметрами)."""
    u = norm_url(url)
    cols = ", ".join(_VAC_COLS)
    row = con.execute(f"SELECT {cols} FROM vacancies WHERE url=? OR url=? OR url LIKE ?", (url, u, u + "?%")).fetchone()
    return dict(zip(_VAC_COLS, row, strict=True)) if row else None


def salary_stats(con, days: int = 90, target: float | None = None) -> dict:
    """Аналитика зарплат по увиденным вакансиям за `days` дней (верх вилки на руки, ₽; дубли не учитываются).
    -> {"roles": [(роль, n, p25, медиана, p75)], "weeks": [(неделя, n, медиана)], "shown": доля с вилкой,
        "above_target": доля вилок ≥ цели}."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = con.execute("SELECT role, net_top, first_seen FROM vacancies WHERE dup_of IS NULL AND last_seen >= ?",
                       (since,)).fetchall()
    with_sal = [(r, n, d) for r, n, d in rows if n]

    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None

    by_role: dict[str, list[float]] = {}
    by_week: dict[str, list[float]] = {}
    for role, net, first in with_sal:
        by_role.setdefault(role or "—", []).append(net)
        try:
            y, w, _ = datetime.strptime(first[:10], "%Y-%m-%d").isocalendar()
            by_week.setdefault(f"{y}-W{w:02d}", []).append(net)
        except (TypeError, ValueError):
            pass
    roles = sorted(((r, len(x), q(x, .25), q(x, .5), q(x, .75)) for r, x in by_role.items()), key=lambda t: -t[1])
    weeks = [(w, len(x), q(x, .5)) for w, x in sorted(by_week.items())]
    nets = [n for _, n, _ in with_sal]
    return {"roles": roles, "weeks": weeks, "total": len(rows), "with_salary": len(nets),
            "shown": round(100 * len(nets) / len(rows)) if rows else None,
            "median": q(nets, .5),
            "above_target": round(100 * sum(n >= target for n in nets) / len(nets)) if nets and target else None}


def known_keys(con) -> set:
    return {(s, i) for s, i in con.execute("SELECT source, id FROM vacancies")}


def get_detail(con, source, vid):
    row = con.execute("SELECT descr, english, years FROM details WHERE source=? AND id=?", (source, vid)).fetchone()
    if not row:
        return None
    return {"desc": row[0], "english": json.loads(row[1]) if row[1] else None, "years": row[2]}


def put_detail(con, source, vid, d, day):
    con.execute("INSERT OR REPLACE INTO details VALUES (?,?,?,?,?,?)",
                (source, vid, d["desc"], json.dumps(d["english"], ensure_ascii=False) if d["english"] else None,
                 d["years"], day))
    con.commit()


# ---------------------------------------------------------------- воронка
def set_status(con, url, title, company, status, origin, at=None, source="", note="") -> bool:
    """Записать событие и обновить статус отклика. -> True, если что-то изменилось."""
    at = at or now()
    key = app_key(url, title, company)
    if not key or key == "|":
        return False
    cur = con.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)", (key, at, status, origin, note))
    row = con.execute("SELECT status FROM applications WHERE key=?", (key,)).fetchone()
    if row is None:
        con.execute("INSERT INTO applications VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (key, norm_url(url) or url or "", title, company, source, status,
                     at if status == "applied" else None, at, note, origin))
        con.commit()
        return True
    old = row[0]
    upgrade = status in TERMINAL or (old not in TERMINAL and STATUS_RANK.get(status, 0) > STATUS_RANK.get(old, 0))
    if upgrade and status != old:
        con.execute("UPDATE applications SET status=?, updated_at=?, title=COALESCE(NULLIF(title,''),?), "
                    "company=COALESCE(NULLIF(company,''),?) WHERE key=?", (status, at, title, company, key))
    if status == "applied":
        con.execute("UPDATE applications SET applied_at=COALESCE(applied_at, ?) WHERE key=?", (at, key))
    con.commit()
    return cur.rowcount > 0 or (upgrade and status != old)


def applications(con) -> list[dict]:
    cols = ["key", "url", "title", "company", "source", "status", "applied_at", "updated_at", "note", "origin"]
    return [dict(zip(cols, r, strict=True)) for r in con.execute(f"SELECT {', '.join(cols)} FROM applications")]


def applied_index(con):
    """Для пометки вакансий: (множество ключей-ссылок, список (title, company, status) для нечёткого сравнения)."""
    apps = applications(con)
    by_key = {a["key"]: a["status"] for a in apps}
    fuzzy = [(norm_text(a["title"]), norm_text(a["company"]), a["status"]) for a in apps]
    return by_key, fuzzy


def applied_status(v: dict, index, threshold: float = 0.82) -> str:
    """Статус отклика для вакансии: по ссылке, иначе по компании + похожему названию. '' — не откликался."""
    by_key, fuzzy = index
    st = by_key.get(app_key(v.get("url"), v.get("title", ""), v.get("company", "")))
    if st:
        return st
    vt, vc = norm_text(v.get("title")), norm_text(v.get("company"))
    if not vc:
        return ""
    for t, c, status in fuzzy:
        if c and (c in vc or vc in c) and SequenceMatcher(None, vt, t).ratio() >= threshold:
            return status
    return ""


def funnel(con) -> dict:
    """Сводка воронки: число по статусам, по источникам, среднее время до ответа."""
    apps = applications(con)
    by_status: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}
    for a in apps:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        src = a["source"] or "другое"
        d = by_source.setdefault(src, {})
        d[a["status"]] = d.get(a["status"], 0) + 1
    waits = []
    for a in apps:
        if a["applied_at"] and a["status"] in ("viewed", "invited", "offer", "rejected") and a["updated_at"]:
            try:
                d0 = datetime.strptime(a["applied_at"][:10], "%Y-%m-%d")
                d1 = datetime.strptime(a["updated_at"][:10], "%Y-%m-%d")
                waits.append((d1 - d0).days)
            except ValueError:
                pass
    silent = [a for a in apps if a["status"] == "applied" and a["applied_at"]
              and (datetime.now() - datetime.strptime(a["applied_at"][:10], "%Y-%m-%d")).days >= 7]
    return {"total": len(apps), "by_status": by_status, "by_source": by_source,
            "median_wait": sorted(waits)[len(waits) // 2] if waits else None, "silent_7d": silent}
