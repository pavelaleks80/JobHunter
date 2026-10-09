"""Широкий поиск: вакансии с нестандартным названием сверяются с резюме по описанию."""
from datetime import date

from jobhunter.pipeline import wide_filter, wide_precheck
from jobhunter.scoring import Scorer


def _v(title, source="getmatch", **kw):
    v = {"source": source, "id": title, "title": title, "company": "Тест", "text": "", "sal_from": None, "sal_to": None,
         "gross": None, "currency": "RUB", "published": ""}
    v.update(kw)
    return v


def test_scorer_wide(settings):
    s = Scorer(settings.scoring, settings.salary)
    r = s.score(_v("Руководитель службы по цифровым продуктам"), date(2026, 10, 9))
    assert r["wide"] and r["role"] == Scorer.WIDE_LABEL and "нестандартное название +10" in r["why"]
    assert s.score(_v("Руководитель проектов"), date(2026, 10, 9))["wide"] is False   # роль распознана
    assert s.score(_v("Бизнес-аналитик"), date(2026, 10, 9)) is None                  # стоп-слово — отброшено
    assert s.score(_v("Лидер направления", source="hh"), date(2026, 10, 9)) is None   # у hh нет описания
    settings.scoring.wide = False
    assert Scorer(settings.scoring, settings.salary).score(_v("Лидер направления"), date(2026, 10, 9)) is None


def test_wide_precheck_drops_hard_gap_in_title(matcher):
    rows = [{"title": "Руководитель ML-платформы", "wide": True}, {"title": "Лидер направления", "wide": True},
            {"title": "Руководитель ML-проектов", "wide": False}]                     # распознанная роль не трогается
    keep, dropped = wide_precheck(rows, matcher)
    assert dropped == 1 and [v["title"] for v in keep] == ["Лидер направления", "Руководитель ML-проектов"]


def test_wide_filter_keeps_only_fitting():
    def r(title, wide, verdict):
        return {"title": title, "wide": wide, "match": {"verdict": verdict}}
    rows = [r("a", True, "Подходит"), r("b", True, "Частично"), r("c", True, "Проверь вручную"), r("d", True, "Не подходит"),
            r("e", False, "Не подходит")]                                             # обычные — без изменений
    keep, checked, kept = wide_filter(rows)                                      # по умолчанию — только «Подходит»
    assert [v["title"] for v in keep] == ["a", "e"] and (checked, kept) == (4, 1)
    keep, _, kept = wide_filter(rows, "Частично")
    assert [v["title"] for v in keep] == ["a", "b", "e"] and kept == 2
