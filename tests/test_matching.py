import pytest

from jobhunter.matching import extract
from jobhunter.profile.schema import Profile, Rule


def test_classify(matcher):
    assert matcher.classify("Опыт управления ИТ-проектами от 5 лет")[0] == "yes"
    assert matcher.classify("Опыт управления ИТ-проектами от 15 лет")[0] == "no"          # стаж больше
    assert matcher.classify("Опыт работы продакт-менеджером от трех лет")[0] == "no"      # по области: 2 года
    assert matcher.classify("Опыт работы с Jira, Confluence")[0] == "yes"
    assert matcher.classify("Опыт ML-проектов")[0] == "no"
    assert matcher.classify("Знание SQL")[0] == "partial"
    assert matcher.classify("Используете ИИ в работе")[0] == "gap"
    assert matcher.classify("Коммуникабельность")[0] == "soft"
    assert matcher.classify("Опыт в маркетинге или управлении проектами")[0] == "partial"  # альтернатива закрыта


def test_english_and_education(matcher):
    assert matcher.classify("English B1")[0] == "yes"
    assert matcher.classify("Английский язык Upper-Intermediate")[0] == "no"
    assert matcher.classify("Высшее техническое образование")[0] == "yes"
    assert matcher.classify("Высшее экономическое образование")[0] == "partial"
    assert matcher.classify("Наличие высшего образования")[0] == "yes"
    # «ценообразование» — не требование к образованию
    assert "образование" not in (matcher.classify("Понимание ценообразования")[1] or "")
    assert matcher.classify("Умеешь решать проблемы, а не создавать их")[0] == "soft"


def test_match_verdicts(matcher):
    r = matcher.match(["Опыт управления проектами от 5 лет", "Опыт внедрения ERP", "Jira", "Управление бюджетом"])
    assert r["verdict"] == "Подходит" and r["fit"] == 100
    r = matcher.match(["Опыт управления проектами", "Опыт ML", "Опыт мобильной разработки", "Jira"])
    assert r["verdict"] == "Не подходит" and len(r["hard"]) == 2
    assert matcher.match(["Опыт управления проектами"])["verdict"] == "Проверь вручную"
    r = matcher.match(["Опыт управления проектами", "Jira", "Риски"], english_level={"name": "B2 — Upper"})
    assert r["verdict"] == "Не подходит" and r["stop"]
    assert matcher.match_title("Руководитель ML-проектов")["verdict"] == "Не подходит"


def test_extract():
    must, nice = extract("<b>Требования:</b><ul><li>Опыт управления проектами от 3 лет</li>"
                         "<li>Английский B2 (будет преимуществом)</li></ul><b>Условия:</b><ul><li>ДМС</li></ul>")
    assert must == ["Опыт управления проектами от 3 лет"] and len(nice) == 1


def test_empty_alternative_rejected():
    with pytest.raises(ValueError):
        Rule(match="jira||confluence")
    with pytest.raises(ValueError):
        Profile(english="Fluent")
