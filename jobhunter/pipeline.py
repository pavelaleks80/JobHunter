"""
pipeline.py — один ежедневный запуск:
  0. отметки «Статус» из прошлых Excel → база;
  1. сайты (getmatch, Хабр) + почта (подборки hh, отклики Хабра, отказы/ответы hh → воронка);
  2. фильтр по названию и балл;
  3. описание вакансии → требования → сверка с profile.yaml (+ ИИ-судья в режиме hybrid);
  4. Excel + tracker.xlsx + письмо.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import cover, dedup, sources
from .matching import Matcher, extract
from .net import session
from .profile.schema import load_profile
from .report import VERDICT_ORDER, build_html, write_excel
from .scoring import Scorer
from .tracker import db, excel_marks, mail_events, xlsx_import

MAX_FAILS_IN_ROW = 3        # после стольких ошибок подряд сайт в этом запуске больше не опрашиваем


def _match_all(s, con, rows, matcher, settings, run_date, log):
    fetched = failed = 0
    fails_in_row: dict[str, int] = {}
    for v in rows:
        if v["source"] == "hh":
            v["match"] = matcher.match_title(v["title"])
            continue
        d = db.get_detail(con, v["source"], v["id"])
        if d is None and fails_in_row.get(v["source"], 0) < MAX_FAILS_IN_ROW:
            try:
                d = sources.detail(s, settings, v["source"], v["id"])
                db.put_detail(con, v["source"], v["id"], d, run_date)
                fetched += 1
                fails_in_row[v["source"]] = 0
                time.sleep(0.3)                     # вежливо к сайту
            except Exception as e:                  # noqa: BLE001 — сверяем по короткому тексту
                fails_in_row[v["source"]] = fails_in_row.get(v["source"], 0) + 1
                log.info("detail %s %s: %s", v["source"], v["id"], e)
        if d is None:                               # не загрузилось — сверяем по короткому тексту, догрузим завтра
            failed += 1
            d = {"desc": v["text"], "english": None, "years": None}
        must, nice = extract(d["desc"])
        v["match"] = matcher.match(must, nice, d["english"], d["years"])
        v["_must"] = must
    return fetched, failed


def _judge(con, rows, matcher, settings, profile, log):
    from .llm import LLMClient, LLMError
    from .matching import judge
    try:
        client = LLMClient.from_settings(settings)
    except LLMError as e:
        log.info("judge off: %s", e)
        return f"ИИ-судья выключен: {e}"
    n = 0
    for v in rows:
        m = v.get("match") or {}
        if v["source"] == "hh" or not m.get("unknown"):
            continue
        try:
            verdicts = judge.judge(client, con, profile, m["unknown"])
            v["match"] = judge.apply(m, verdicts, matcher)
            n += 1
        except LLMError as e:
            log.info("judge %s: %s", v["id"], e)
            return f"ИИ-судья: ошибка {e}"
    return f"ИИ-судья: дооценено {n} вакансий"


def run(settings, send_mail=True, all_new=False, echo=print):
    settings.ensure_dirs()
    logging.basicConfig(filename=settings.log_dir / "jobhunter.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("jobhunter")
    run_dt = datetime.now()
    run_date = run_dt.strftime("%Y-%m-%d")
    profile = load_profile(settings.profile_path)
    matcher = Matcher(profile, settings.matching)
    scorer = Scorer(settings.scoring, settings.salary)
    con = db.connect(settings.db_path)
    s = session(settings.cache_dir, settings.user_agent)

    n_marks = excel_marks.harvest(con, settings.output_dir)
    echo(f"Отметки из Excel: новых {n_marks}")
    ti = settings.tracker_import
    if ti.enabled:
        try:
            n_rows, n_changed = xlsx_import.import_tracker(con, ti)
            echo(f"[OK] ваш трекер {Path(ti.path).name}: строк {n_rows}, изменений в воронке {n_changed}")
        except Exception as e:          # noqa: BLE001 — трекер не должен ронять запуск
            echo(f"[!!] ваш трекер: {e}")
            log.info("tracker_import: %s", e)

    raw, status = sources.collect(s, settings)
    if settings.sources.mail.enabled:
        try:
            mail = mail_events.fetch(settings)
            raw += mail["vacancies"]
            changed = sum(db.set_status(con, url, t, c, st, "почта", at=day, source=src)
                          for url, t, c, st, src, day in mail["events"])
            status["mail"] = (True, f"{mail['stats']}; изменений в воронке {changed}")
        except Exception as e:          # noqa: BLE001 — почта не должна ронять отчёт
            status["mail"] = (False, f"почта: {e}"[:300])
    for k, (ok, msg) in status.items():
        echo(f"[{'OK' if ok else '!!'}] {k}: {msg}")
        log.info("source %s ok=%s %s", k, ok, msg)

    rows, dropped = [], 0
    for v in raw:
        sc = scorer.score(v, run_dt.date())
        if sc is None:
            dropped += 1
            continue
        rows.append({**v, **sc})
    echo(f"Собрано {len(raw)}, подходит по названию {len(rows)}, отброшено {dropped}")

    known = db.known_keys(con)
    index = db.applied_index(con)
    for v in rows:
        v["is_new"] = all_new or (v["source"], v["id"]) not in known
        v["applied"] = db.applied_status(v, index, settings.matching.fuzzy_applied)
    rows, n_dup = dedup.merge(rows)
    if n_dup:
        echo(f"Дубли с других площадок склеены: {n_dup}")

    fetched, failed = _match_all(s, con, rows, matcher, settings, run_date, log)
    echo(f"Описания: загружено {fetched}, из кэша {len(rows) - fetched - failed}, не удалось {failed}")
    if settings.matching.mode in ("hybrid", "llm"):
        msg = _judge(con, rows, matcher, settings, profile, log)
        status["ai"] = (not msg.startswith("ИИ-судья: ошибка"), msg)
        echo(msg)
    db.upsert_vacancies(con, rows, run_date)

    rows.sort(key=lambda v: (VERDICT_ORDER[v["match"]["verdict"]], -(v["match"]["fit"] or 0), -v["score"]))
    cnt = Counter(v["match"]["verdict"] for v in rows if not v["applied"])
    echo("Без отклика: " + ", ".join(f"{k} {cnt.get(k, 0)}" for k in VERDICT_ORDER))

    for v in rows:
        v["cover"] = cover.existing(settings, v["source"], v["id"])
    funnel = db.funnel(con)
    salaries = db.salary_stats(con, target=settings.salary.target)
    path = write_excel(rows, status, run_dt, settings.output_dir, funnel, salaries, settings.salary.target)
    trk = excel_marks.export(con, settings.tracker_path)
    echo(f"Excel: {path}\nТрекер: {trk}")
    log.info("rows=%d %s excel=%s", len(rows), dict(cnt), path)

    if send_mail and settings.email.enabled:
        from .notify.email import send
        html, (n, n_new) = build_html(rows, status, run_dt, settings.email.top_n, settings.email.top_n_mail_source,
                                      funnel, salaries, settings.salary.target)
        bad = [k for k, (ok, _) in status.items() if not ok]
        subj = f"Вакансии: {n} подходящих, из них новых {n_new} ({run_dt:%d.%m.%Y})" + (f" ⚠ {', '.join(bad)}" if bad else "")
        ok, msg = send(settings, subj, html, path)
        echo(f"[{'OK' if ok else '!!'}] письмо: {msg}")
        log.info("email ok=%s %s", ok, msg)
    con.close()
    return {"rows": rows, "status": status, "excel": path}

