from jobhunter import cover
from jobhunter.profile.schema import load_profile
from jobhunter.tracker import db

DESC = ("<b>Требования:</b><ul><li>Опыт управления ИТ-проектами от 5 лет</li><li>Опыт внедрения ERP</li>"
        "<li>Опыт ML-проектов</li></ul><b>Условия:</b><ul><li>ДМС</li></ul>")
RESUME = "Анна Смирнова. Руководитель ИТ-проектов, 12 лет. Внедрила 1С:ERP на 3 заводах. " * 5


class FakeLLM:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def chat(self, system, user):
        self.prompts.append((system, user))
        return self.answer


def test_make_and_write(settings, matcher):
    con = db.connect(settings.db_path)
    db.upsert_vacancies(con, [{"source": "habr", "id": "7", "title": "Руководитель проектов ERP", "company": "Завод",
                               "url": "https://career.habr.com/vacancies/7", "published": "", "sal_from": None,
                               "sal_to": None, "currency": "RUB", "gross": None, "score": 80, "why": ""}], "2026-10-08")
    db.put_detail(con, "habr", "7", {"desc": DESC, "english": None, "years": None}, "2026-10-08")
    vac, detail = cover.vacancy_for(con, settings, None, "https://career.habr.com/vacancies/7?utm=1")
    assert vac["title"] == "Руководитель проектов ERP" and "ERP" in detail["desc"]

    settings.cover.signature = "Анна, @anna"
    llm = FakeLLM("```\nТема: отклик\nЗдравствуйте! Внедряла 1С:ERP на трёх заводах. [Ваше имя]\n```")
    text, match = cover.make(llm, settings, load_profile(settings.profile_path), matcher, RESUME, vac, detail)
    system, user = llm.prompts[0]
    assert "Не придумывай" in system
    assert "Опыт внедрения ERP" in user and "Завод" in user and "Внедрила 1С:ERP" in user
    assert "нет опыта ML" in user                                        # пробел передан модели
    assert text == "Здравствуйте! Внедряла 1С:ERP на трёх заводах.\n\nАнна, @anna"
    p = cover.write(settings, vac, text, match)
    assert p == cover.existing(settings, "habr", "7")
    body = p.read_text(encoding="utf-8")
    assert "https://career.habr.com/vacancies/7" in body and "Внедряла" in body


def test_unknown_url(settings):
    con = db.connect(settings.db_path)
    vac, detail = cover.vacancy_for(con, settings, None, "https://hh.ru/vacancy/555?loginkey=X", "РП", "Тест")
    assert (vac["source"], vac["id"], vac["url"]) == ("hh", "555", "https://hh.ru/vacancy/555")
    assert detail["desc"] == ""
