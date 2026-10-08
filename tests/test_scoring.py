from datetime import date

from jobhunter.scoring import Scorer


def _scorer(settings):
    return Scorer(settings.scoring, settings.salary)


def test_roles(settings):
    s = _scorer(settings)
    assert s.role_of("Руководитель проектов")[1] == "руководитель проектов"
    assert s.role_of("Senior Project Manager")[1] == "Project Manager"
    assert s.role_of("Владелец продукта (Product Owner)")[1] == "Product Owner"
    for t in ("Junior Project Manager", "Младший руководитель проектов", "Java-разработчик", "Бизнес-аналитик"):
        assert s.role_of(t) is None, t


def test_score_and_salary(settings):
    s = _scorer(settings)
    v = {"title": "Руководитель проектов ИБ", "company": "Касперский", "text": "госсектор",
         "sal_from": 300000, "sal_to": 400000, "gross": False, "currency": "RUB", "published": "2026-10-08"}
    r = s.score(v, date(2026, 10, 8))
    assert r["score"] == 86 and "целевая компания" in r["why"]
    low = s.score({**v, "company": "Ромашка", "text": "", "sal_from": 100000, "sal_to": 120000,
                   "published": "2026-09-01"}, date(2026, 10, 8))
    assert "НИЖЕ ПОЛА" in low["why"] and low["score"] < 50
    assert s.net_salary({"sal_to": 100000, "gross": True, "currency": "RUB"}) == 87000
