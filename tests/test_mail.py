"""Разбор писем площадок. Образцы — обезличенные копии структуры реальных писем (октябрь 2026)."""
from email.message import EmailMessage

from jobhunter.tracker import mail_events as me

KEY = "&loginkey=SECRET"

HH_SUB = ("<table><tr><td><a href=\"https://hh.ru/vacancy/111?utm_content=vacancy_name" + KEY + "\">"
          "<span>Менеджер проекта</span></a></td></tr><tr><td>от 328 600 ₽ за месяц</td></tr>"
          "<tr><td>Ромашка, Москва, м. Арбатская</td></tr>"
          "<tr><td><a href=\"https://hh.ru/vacancy/111?utm_content=butt" + KEY + "\">Посмотреть вакансию</a></td></tr>"
          "<tr><td><a href=\"https://hh.ru/vacancy/222?utm_content=vacancy_name\">Руководитель проекта</a></td></tr>"
          "<tr><td>Лютик, Санкт-Петербург</td></tr></table>")

HH_REJECT = ("<div>Здравствуйте!<br/><br/>К сожалению, сейчас мы не готовы пригласить вас.</div>"
             "<div>Вакансия: Руководитель цифрового продукта</div><div>Компании: Банк Тест. Центральный офис</div>"
             "<div><a href=\"https://hh.ru/vacancy/333?utm_source=email" + KEY + "\">Посмотреть вакансию</a></div>")

HH_RESPONSE = ("<table><tr><td>Сообщение от работодателя</td></tr><tr><td>Вакансия: Менеджер по проектам</td></tr>"
               "<tr><td>Компания: ТестБанк. Головной офис</td></tr>"
               "<tr><td><a href=\"https://hh.ru/vacancy/444?x=1" + KEY + "\">Перейти к вакансии</a></td></tr></table>")

HABR_PLAIN = ("Здравствуйте, Анна!\n\nВы откликнулись на вакансию Product owner (https://career.habr.com/vacancies/1000000001"
              "?utm_source=mail) компании ТестБанк (https://career.habr.com/companies/test-bank). Уведомление ушло куратору.")


def _msg(sender, subject, body, html=True):
    m = EmailMessage()
    m["From"], m["Subject"], m["Date"] = sender, subject, "Wed, 08 Oct 2026 10:00:00 +0300"
    if html:
        m.set_content(body, subtype="html")
    else:
        m.set_content(body)
    return m


def test_hh_subscription():
    assert me.parse_hh_subscription(HH_SUB) == [("111", "Менеджер проекта", "Ромашка", "Москва", 328600, None),
                                                ("222", "Руководитель проекта", "Лютик", "Санкт-Петербург", None, None)]
    r = me.parse_message(_msg('"hh.ru" <noreply@hh.ru>', "Вакансии по подписке: Все вакансии", HH_SUB))
    assert r["kind"] == "hh_subscription" and len(r["vacancies"]) == 2
    assert all("loginkey" not in v["url"] for v in r["vacancies"])


def test_hh_rejection_and_response():
    r = me.parse_message(_msg("noreply@hh.ru", "Работодатель не готов пригласить вас на собеседование", HH_REJECT))
    assert r["events"] == [("https://hh.ru/vacancy/333", "Руководитель цифрового продукта",
                            "Банк Тест. Центральный офис", "rejected", "hh")]
    r = me.parse_message(_msg("noreply@hh.ru", "Вам написали по вакансии Менеджер по проектам", HH_RESPONSE))
    assert r["events"][0][3] == "viewed" and r["events"][0][2] == "ТестБанк. Головной офис"


def test_habr_applied_plain_and_html():
    r = me.parse_message(_msg("Хабр Карьера <noreply@career.habr.com>",
                              "Вы откликнулись на вакансию Product owner на Хабр Карьере", HABR_PLAIN, html=False))
    assert r["events"] == [("https://career.habr.com/vacancies/1000000001", "Product owner", "ТестБанк", "applied", "habr")]
    html = ("<p>Вы откликнулись на вакансию <a href=\"https://career.habr.com/vacancies/77?utm=1\">Владелец продукта</a> "
            "компании <a href=\"https://career.habr.com/companies/t\">Тест</a>.</p>")
    assert me.parse_habr_applied(html) == ("https://career.habr.com/vacancies/77", "Владелец продукта", "Тест")


def test_habr_tracking_links():
    """Реальная вёрстка Хабра: ссылки через email_tracking с закодированным адресом вакансии."""
    trk = "https://career.habr.com/email_tracking/messages/TOKEN/click?signature=SIG&amp;url="
    html = ("<p>Здравствуйте, Анна!</p><p>Вы откликнулись на вакансию <a href=\"" + trk +
            "https%3A%2F%2Fcareer.habr.com%2Fvacancies%2F1000000001%3Futm_campaign%3Demail\">Product owner</a> компании "
            "<a href=\"" + trk + "https%3A%2F%2Fcareer.habr.com%2Fcompanies%2Ftest-bank%3Futm%3D1\">ТестБанк</a>.</p>")
    assert me.parse_habr_applied(html) == ("https://career.habr.com/vacancies/1000000001", "Product owner", "ТестБанк")


def test_unknown_letter_ignored():
    r = me.parse_message(_msg("noreply@hh.ru", "Ваше резюме прошло модерацию", "<p>ok</p>"))
    assert r["kind"] is None and not r["events"]
