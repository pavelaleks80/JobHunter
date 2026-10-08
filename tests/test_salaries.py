import sqlite3
from datetime import date, datetime

from jobhunter.scoring import Scorer
from jobhunter.tracker import db


def _row(vid, role, net, **kw):
    r = {"source": "getmatch", "id": vid, "title": "РП", "company": "Тест", "url": f"https://getmatch.ru/vacancies/{vid}",
         "published": "", "sal_from": None, "sal_to": net, "currency": "RUB", "gross": False, "score": 50, "why": "",
         "role": role, "net_top": net}
    r.update(kw)
    return r


def test_salary_stats(tmp_path):
    con = db.connect(tmp_path / "j.db")
    today = datetime.now().strftime("%Y-%m-%d")
    rows = [_row(str(i), "РП", 200000 + i * 50000) for i in range(5)]           # 200…400 тыс.
    rows += [_row("p1", "PO", 250000), _row("x", "РП", None)]
    rows[0]["dups"] = [_row("dup", "РП", 999000, source="hh")]                  # дубль в статистику не попадает
    db.upsert_vacancies(con, rows, today)
    st = db.salary_stats(con, target=300000)
    roles = {r[0]: r for r in st["roles"]}
    assert roles["РП"][1] == 5 and roles["РП"][3] == 300000                     # медиана
    assert st["total"] == 7 and st["with_salary"] == 6 and st["shown"] == 86
    assert st["above_target"] == 50                                              # 300, 350, 400 из 6
    assert st["weeks"] and st["weeks"][0][1] == 6


def test_migration_from_0_1_0(tmp_path):
    """База 0.1.0 без колонок role/net_top/dup_of открывается и дополняется."""
    p = tmp_path / "old.db"
    old = sqlite3.connect(p)
    old.execute("CREATE TABLE vacancies(source TEXT, id TEXT, title TEXT, company TEXT, url TEXT, published TEXT, "
                "sal_from REAL, sal_to REAL, currency TEXT, gross INTEGER, score INTEGER, why TEXT, verdict TEXT, "
                "fit INTEGER, first_seen TEXT, last_seen TEXT, PRIMARY KEY(source, id))")
    old.execute("INSERT INTO vacancies VALUES ('habr','1','РП','Т','u','',NULL,NULL,'RUB',NULL,1,'',NULL,NULL,'2026-10-01','2026-10-01')")
    old.commit()
    old.close()
    con = db.connect(p)
    cols = {r[1] for r in con.execute("PRAGMA table_info(vacancies)")}
    assert {"role", "net_top", "dup_of"} <= cols
    assert db.find_vacancy(con, "u")["title"] == "РП"


def test_blacklist(settings):
    settings.scoring.blacklist_companies = ["ромашк"]
    s = Scorer(settings.scoring, settings.salary)
    v = {"title": "Руководитель проектов", "company": "ООО Ромашка", "text": "", "sal_from": None, "sal_to": None,
         "gross": None, "currency": "RUB", "published": ""}
    assert s.score(v, date(2026, 10, 8)) is None
    assert s.score({**v, "company": "Лютик"}, date(2026, 10, 8)) is not None
