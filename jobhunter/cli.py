"""
cli.py — команда `jobhunter` (или `python -m jobhunter`).

  (Windows без Scripts в PATH: python -m jobhunter <команда>)
  jobhunter init                 создать workspace/: config.yaml, .env, папка resume/
  jobhunter profile              резюме (PDF/DOCX/TXT) → profile.yaml через LLM  (--template — заготовка без LLM)
  jobhunter run                  собрать вакансии, сверить с профилем, Excel + письмо  (--no-email, --all-new)
  jobhunter applied <url> [...]  отметить отклик (--status invited|rejected|offer|ignored|viewed)
  jobhunter stats                воронка откликов
  jobhunter import-tracker       перенести отклики из вашего Excel-трекера (секция tracker_import в config.yaml)
  jobhunter salaries             зарплаты по ролям и неделям (верх вилки на руки)
  jobhunter cover <url> [...]    сопроводительное письмо под вакансию (--fit N — для N лучших без отклика)
  jobhunter check                проверить настройки: профиль, почта, LLM, доступность сайтов
Рабочая папка: --workspace или переменная JOBHUNTER_WORKSPACE (по умолчанию ./workspace).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path

from .config import default_workspace, load_settings


def _examples_dir() -> Path:
    """Примеры настроек — внутри пакета (jobhunter/examples), работают и после обычного pip install."""
    return Path(str(resources.files("jobhunter"))) / "examples"


def cmd_init(args):
    ws = args.workspace
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "resume").mkdir(exist_ok=True)
    ex = _examples_dir()
    for src, dst in (("config.example.yaml", "config.yaml"), ("env.example", ".env")):
        target = ws / dst
        if target.exists():
            print(f"  уже есть: {target}")
            continue
        shutil.copy(ex / src, target)
        print(f"  создан:   {target}")
    print(f"\nДальше:\n  1. положите резюме (.pdf/.docx/.txt) в {ws / 'resume'}\n"
          f"  2. заполните {ws / '.env'} (почта и ключ LLM)\n"
          f"  3. jobhunter profile   → проверьте {ws / 'profile.yaml'}\n"
          f"  4. отредактируйте роли и ключевые слова в {ws / 'config.yaml'}\n"
          f"  5. jobhunter check  →  jobhunter run")
    return 0


def cmd_profile(args):
    from .profile.build import build_from_text, template
    from .profile.extract_text import extract, find_resume
    from .profile.schema import save_profile
    s = load_settings(args.workspace)
    s.ensure_dirs()
    out = s.profile_path
    if out.exists() and not args.force:
        print(f"{out} уже есть. Перезаписать: jobhunter profile --force")
        return 1
    if args.template:
        save_profile(template(), out)
        print(f"Заготовка профиля: {out} — заполните её руками.")
        return 0
    from .llm import LLMClient, LLMError
    try:
        path = find_resume(s.resume_path)
        text = extract(path)
        print(f"Резюме: {path.name} — {len(text)} символов")
        client = LLMClient.from_settings(s)
        print(f"Строю профиль ({client.model})…")
        prof = build_from_text(client, text)
    except (FileNotFoundError, ValueError, LLMError) as e:
        print(f"[!!] {e}")
        return 1
    save_profile(prof, out)
    print(f"Готово: {out}\n  навыков {len(prof.skills)}, частично {len(prof.partial)}, скрытых {len(prof.hidden)}, "
          f"пробелов {len(prof.missing)}; стаж {prof.years.default} лет, английский {prof.english}\n"
          f"Проверьте файл: это черновик, правила можно поправить руками.")
    return 0


def cmd_run(args):
    from .pipeline import run
    s = load_settings(args.workspace)
    run(s, send_mail=not args.no_email, all_new=args.all_new)
    return 0


def cmd_applied(args):
    from .tracker import db
    s = load_settings(args.workspace)
    s.ensure_dirs()
    con = db.connect(s.db_path)
    for url in args.urls:
        row = con.execute("SELECT title, company, source FROM vacancies WHERE url=? OR url LIKE ?",
                          (url, db.norm_url(url) + "%")).fetchone()
        title, company, source = row if row else (args.title or "", args.company or "", "")
        changed = db.set_status(con, url, title, company, args.status, "cli", source=source)
        print(f"{'✓' if changed else '·'} {db.STATUS_RU[args.status]}: {title or url}")
    return 0


def cmd_stats(args):
    from .tracker import db
    s = load_settings(args.workspace)
    con = db.connect(s.db_path)
    f = db.funnel(con)
    print(f"Откликов в базе: {f['total']}")
    for k in ("applied", "viewed", "invited", "offer", "rejected", "ignored"):
        print(f"  {db.STATUS_RU[k]:<14} {f['by_status'].get(k, 0)}")
    if f["median_wait"] is not None:
        print(f"Медиана дней до ответа: {f['median_wait']}")
    print(f"Без ответа 7+ дней: {len(f['silent_7d'])}")
    for src, d in sorted(f["by_source"].items()):
        print(f"  {src:<10} " + ", ".join(f"{db.STATUS_RU.get(k, k)} {n}" for k, n in d.items()))
    return 0


def cmd_import_tracker(args):
    from .tracker import db, xlsx_import
    s = load_settings(args.workspace)
    ti = s.tracker_import
    if not ti.path:
        print("Не задан путь: секция tracker_import в config.yaml (см. docs/setup.md, «Свой трекер откликов»)")
        return 1
    con = db.connect(s.db_path)
    try:
        n_rows, n_changed = xlsx_import.import_tracker(con, ti)
    except (FileNotFoundError, ValueError) as e:
        print(f"[!!] {e}")
        return 1
    print(f"Строк в трекере: {n_rows}; изменений в воронке: {n_changed}")
    f = db.funnel(con)
    print("Воронка: " + ", ".join(f"{db.STATUS_RU[k]} {f['by_status'].get(k, 0)}"
                                  for k in ("applied", "viewed", "invited", "offer", "rejected", "ignored")))
    if not ti.enabled:
        print("Чтобы читать трекер при каждом запуске: tracker_import → enabled: true в config.yaml")
    return 0


def cmd_salaries(args):
    from .tracker import db
    s = load_settings(args.workspace)
    con = db.connect(s.db_path)
    st = db.salary_stats(con, days=args.days, target=s.salary.target)
    k = lambda x: f"{round(x / 1000)}" if x else "—"      # noqa: E731
    print(f"Вакансий за {args.days} дн.: {st['total']}, с вилкой {st['with_salary']} ({st['shown'] or 0}%), "
          f"медиана верха вилки на руки {k(st['median'])} тыс.")
    if st["above_target"] is not None:
        print(f"Вилку ≥ вашей цели {k(s.salary.target)} тыс. дают {st['above_target']}% вакансий")
    print(f"\n{'Роль':<28}{'n':>5}{'25%':>8}{'медиана':>9}{'75%':>8}")
    for role, n, p25, med, p75 in st["roles"]:
        print(f"{role[:27]:<28}{n:>5}{k(p25):>8}{k(med):>9}{k(p75):>8}")
    if st["weeks"]:
        print("\nПо неделям: " + ", ".join(f"{w} — {k(m)} (n={n})" for w, n, m in st["weeks"][-8:]))
    return 0


def cmd_cover(args):
    from . import cover
    from .llm import LLMClient, LLMError
    from .matching import Matcher
    from .net import session
    from .profile.extract_text import extract, find_resume
    from .profile.schema import load_profile
    from .tracker import db
    s = load_settings(args.workspace)
    s.ensure_dirs()
    con = db.connect(s.db_path)
    urls = list(args.urls)
    if args.fit:
        index = db.applied_index(con)
        rows = con.execute("SELECT url, title, company, source, id FROM vacancies WHERE dup_of IS NULL AND "
                           "verdict IN ('Подходит', 'Частично') AND source != 'hh' "
                           "ORDER BY verdict = 'Подходит' DESC, fit DESC, score DESC, last_seen DESC").fetchall()
        for url, title, company, source, vid in rows:
            if len(urls) >= args.fit:
                break
            if cover.existing(s, source, vid) or db.applied_status({"url": url, "title": title, "company": company}, index):
                continue
            urls.append(url)
    if not urls:
        print("Нет вакансий: укажите ссылки или --fit N (берутся «Подходит»/«Частично» без отклика и без письма)")
        return 1
    try:
        client = LLMClient.from_settings(s)
        profile = load_profile(s.profile_path)
        resume_text = extract(find_resume(s.resume_path))
    except (LLMError, FileNotFoundError, ValueError) as e:
        print(f"[!!] {e}")
        return 1
    matcher = Matcher(profile, s.matching)
    sess = session(s.cache_dir, s.user_agent)
    code = 0
    for url in urls:
        try:
            vac, detail = cover.vacancy_for(con, s, sess, url, args.title or "", args.company or "")
            if cover.existing(s, vac["source"], vac["id"]) and not args.force:
                print(f"· уже есть: {cover.cover_path(s, vac['source'], vac['id'])} (--force — переписать)")
                continue
            text, match = cover.make(client, s, profile, matcher, resume_text, vac, detail)
            p = cover.write(s, vac, text, match)
            print(f"✓ {vac.get('title') or url} → {p}")
        except (LLMError, ValueError) as e:
            print(f"[!!] {url}: {e}")
            code = 1
        except Exception as e:      # noqa: BLE001 — сеть/сайт: остальные письма всё равно пишем
            print(f"[!!] {url}: {str(e)[:200]}")
            code = 1
    return code


def cmd_check(args):
    from .net import session
    from .profile.schema import load_profile
    s = load_settings(args.workspace)
    ok = True

    def line(good, text):
        nonlocal ok
        ok &= bool(good)
        print(f"[{'OK' if good else '!!'}] {text}")

    line((s.workspace / "config.yaml").exists(), f"config.yaml: {s.workspace / 'config.yaml'}")
    line(bool(s.scoring.roles), f"ролей в config.yaml: {len(s.scoring.roles)}")
    try:
        p = load_profile(s.profile_path)
        line(True, f"profile.yaml: {len(p.skills)} навыков, стаж {p.years.default}, английский {p.english}")
    except Exception as e:      # noqa: BLE001
        line(False, f"profile.yaml: {e}")
    sess = session(s.cache_dir, s.user_agent)
    for name, url in (("getmatch", "https://getmatch.ru/api/offers?limit=1"),
                      ("Хабр Карьера", "https://career.habr.com/api/frontend/vacancies?page=1")):
        try:
            r = sess.get(url, timeout=s.http_timeout)
            line(r.ok, f"{name}: HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            hint = " (Хабр обычно недоступен через VPN)" if "Хабр" in name else " (проверьте интернет)"
            line(False, f"{name}: {str(e)[:120]}{hint}")
    if s.sources.mail.enabled:
        import imaplib
        m = s.sources.mail
        try:
            im = imaplib.IMAP4_SSL(s.secret("IMAP_SERVER") or m.server, 993, timeout=30)
            im.login(s.secret(m.user_env), s.secret(m.password_env).replace(" ", ""))
            from .tracker.mail_events import select_folder
            name = select_folder(im, m.folder)
            im.logout()
            line(True, f"почта IMAP {m.server}: вход OK, папка {m.folder} ({name})")
        except Exception as e:  # noqa: BLE001
            line(False, f"почта IMAP: {str(e)[:160]}")
    ti = s.tracker_import
    if ti.enabled:
        from .tracker import xlsx_import
        try:
            rows = xlsx_import.read_rows(ti)
            line(bool(rows), f"ваш трекер: {Path(ti.path).name}, лист «{ti.sheet}», строк с откликами {len(rows)}")
        except Exception as e:  # noqa: BLE001
            line(False, f"ваш трекер: {e}")
    c = s.email
    smtp_missing = [k for k in (c.login_env, c.password_env) if not s.secret(k)]
    line(not smtp_missing or not c.enabled,
         "SMTP: логин и пароль заданы (пароль не показывается)" if not smtp_missing
         else f"SMTP: нет {', '.join(smtp_missing)} в .env — письмо не уйдёт")
    line(bool(s.secret(s.llm.api_key_env)) or s.matching.mode == "rules",
         f"LLM: модель {s.secret(s.llm.model_env) or '—'}, ключ {'есть' if s.secret(s.llm.api_key_env) else 'нет'}")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobhunter", description="Ежедневный подбор вакансий под ваше резюме")
    ap.add_argument("--workspace", type=Path, default=None, help="рабочая папка (по умолчанию ./workspace)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="создать рабочую папку")
    p = sub.add_parser("profile", help="профиль из резюме")
    p.add_argument("--template", action="store_true", help="заготовка без LLM")
    p.add_argument("--force", action="store_true", help="перезаписать profile.yaml")
    r = sub.add_parser("run", help="ежедневный запуск")
    r.add_argument("--no-email", action="store_true")
    r.add_argument("--all-new", action="store_true", help="считать новыми все вакансии")
    a = sub.add_parser("applied", help="отметить отклик")
    a.add_argument("urls", nargs="+")
    a.add_argument("--status", default="applied", choices=["applied", "viewed", "invited", "offer", "rejected", "ignored"])
    a.add_argument("--title")
    a.add_argument("--company")
    sub.add_parser("stats", help="воронка откликов")
    sub.add_parser("import-tracker", help="отклики из вашего Excel-трекера")
    sa = sub.add_parser("salaries", help="аналитика зарплат")
    sa.add_argument("--days", type=int, default=90)
    c = sub.add_parser("cover", help="сопроводительное письмо")
    c.add_argument("urls", nargs="*")
    c.add_argument("--fit", type=int, default=0, help="написать для N лучших вакансий без отклика")
    c.add_argument("--force", action="store_true", help="переписать готовое письмо")
    c.add_argument("--title")
    c.add_argument("--company")
    sub.add_parser("check", help="проверить настройки")
    args = ap.parse_args(argv)
    args.workspace = (args.workspace or default_workspace()).resolve()
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    return {"init": cmd_init, "profile": cmd_profile, "run": cmd_run, "applied": cmd_applied,
            "stats": cmd_stats, "import-tracker": cmd_import_tracker, "salaries": cmd_salaries, "cover": cmd_cover, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
