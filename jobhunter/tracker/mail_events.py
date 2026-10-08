"""
mail_events.py — вакансии и события воронки из почты (IMAP, только чтение).

Что умеем распознавать (проверено на реальных письмах, октябрь 2026):
  hh.ru  «Вакансии по подписке: …»                → вакансии (источник «hh»; описание не загружается);
  hh.ru  «Работодатель не готов пригласить вас…»  → rejected (есть id вакансии, название, компания);
  hh.ru  «Вам написали по вакансии …», «Сообщение от работодателя», «Вакансия …: вам написали из …»
                                                   → viewed (работодатель ответил; есть id, название, компания);
  Хабр   «Вы откликнулись на вакансию …»           → applied (ссылка на вакансию и компанию).
getmatch о откликах писем не присылает — такие отклики отмечаются в Excel/командой `jobhunter applied`.

Безопасность: ящик открывается readonly, письма читаются через BODY.PEEK (не помечаются прочитанными).
Ссылки hh содержат персональный ключ входа — сохраняется только https://hh.ru/vacancy/<id>.
"""
from __future__ import annotations

import email
import html as _html
import imaplib
import re
import ssl
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from urllib.parse import unquote

from ..sources import vacancy

_TAG = re.compile(r"<[^>]+>")


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", s or ""))).strip("  ⠀|")


def _flat(body: str) -> str:
    body = re.sub(r"<(style|script).*?</\1>", " ", body, flags=re.S | re.I)
    return _txt(re.sub(r"<(?:/td|/div|/p|br|/tr)[^>]*>", "\n", body, flags=re.I))


# ---------------------------------------------------------------- hh: подборка
_VAC_LINK = re.compile(r'<a\b[^>]*href="(https?://(?:[\w-]+\.)?hh\.ru/vacancy/(\d+)[^"]*)"[^>]*>(.*?)</a>', re.I | re.S)
_BUTTON = re.compile(r"посмотреть вакансию|откликнуться|подробнее", re.I)
_SALARY = re.compile(r"₽|руб|за месяц|\$|€", re.I)
_CITY = re.compile(r",\s*(Москва|Санкт-Петербург|Новосибирск|Екатеринбург|Казань|Нижний Новгород|Краснодар|"
                   r"Московская область|Химки|Красногорск|Мытищи|Зеленоград|Россия)\b.*$", re.I)


def _salary(line):
    nums = [int(re.sub(r"\D", "", x)) for x in re.findall(r"\d[\d\s  ]*\d", line)]
    nums = [n for n in nums if n >= 1000]
    if not nums:
        return None, None
    if re.search(r"^\s*до\b", line, re.I):
        return None, nums[0]
    return nums[0], (nums[1] if len(nums) > 1 else None)


def parse_hh_subscription(body: str):
    """-> [(id, название, компания, город, зп_от, зп_до)]."""
    out, seen = [], set()
    links = list(_VAC_LINK.finditer(body))
    for i, m in enumerate(links):
        vid, title = m.group(2), _txt(m.group(3))
        if not title or _BUTTON.search(title) or vid in seen:
            continue
        end = links[i + 1].start() if i + 1 < len(links) else min(len(body), m.end() + 3000)
        tail = [t for t in (_txt(x) for x in re.split(r"<(?:/td|/div|/p|br|/tr)[^>]*>", body[m.end():end], flags=re.I)) if t]
        sal_from = sal_to = None
        comp_line = ""
        for t in tail:
            if _SALARY.search(t) and re.search(r"\d", t):
                sal_from, sal_to = _salary(t)
                continue
            comp_line = t
            break
        cm = _CITY.search(comp_line)
        company, city = (comp_line[:cm.start()], cm.group(1)) if cm else (comp_line, "")
        seen.add(vid)
        out.append((vid, title, company.strip(), city.strip(), sal_from, sal_to))
    return out


# ---------------------------------------------------------------- hh: письмо о конкретной вакансии
def parse_hh_vacancy_letter(body: str):
    """Отказ / «вам написали»: (id, название, компания) или None."""
    m_id = re.search(r"hh\.ru/vacancy/(\d+)", body)
    if not m_id:
        return None
    t = _flat(body)
    m_v = re.search(r"Вакансия:\s*(.+?)(?:\s+Компани[яи]:|$)", t)
    m_c = re.search(r"Компани[яи]:\s*(.+?)(?:\s+(?:Посмотреть|Перейти|Выбрать|Сообщение)|$)", t)
    return m_id.group(1), (m_v.group(1).strip() if m_v else ""), (m_c.group(1).strip() if m_c else "")


# ---------------------------------------------------------------- Хабр: «Вы откликнулись»
_HABR_APPLY = re.compile(r"Вы откликнулись на вакансию\s+(.+?)\s*\(?\s*(https://career\.habr\.com/vacancies/\d+)[^\s)]*\)?\s*"
                         r"компании\s+(.+?)\s*\(?\s*https://career\.habr\.com/companies", re.S)


_HABR_TARGET = re.compile(r"https://career\.habr\.com/(?:vacancies|companies)/[\w-]+")


def _habr_link(url: str) -> str:
    """Ссылка трекинга «…email_tracking…&url=https%3A%2F%2Fcareer.habr.com%2Fvacancies%2F123…» → адрес вакансии."""
    m = _HABR_TARGET.search(unquote(_html.unescape(url)))
    return m.group(0) if m else url


def parse_habr_applied(body: str, subject: str = ""):
    """-> (url, название, компания) или None. Работает и с text/plain, и с HTML; ссылки бывают через редирект трекинга."""
    if "<" in body:
        t = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"{m.group(2)} ({_habr_link(m.group(1))})",
                   body, flags=re.S | re.I)
        t = _txt(t)
    else:
        t = re.sub(r"\s+", " ", re.sub(r"https?://[^\s)]+", lambda m: _habr_link(m.group(0)), body))
    m = _HABR_APPLY.search(t)
    if m:
        title = re.sub(r"\s*\($", "", m.group(1)).strip()
        return m.group(2), title, m.group(3).strip()
    m_url = re.search(r"https://career\.habr\.com/vacancies/(\d+)", unquote(body))
    m_sub = re.search(r"Вы откликнулись на вакансию (.+?) на Хабр Карьере", subject)
    if m_url and m_sub:
        return f"https://career.habr.com/vacancies/{m_url.group(1)}", m_sub.group(1), ""
    return None


# ---------------------------------------------------------------- классификация письма
KINDS = [
    ("hh_subscription", r"noreply@hh\.ru", r"^Вакансии по подписке"),
    ("hh_rejected", r"noreply@hh\.ru", r"не готов пригласить"),
    ("hh_response", r"noreply@hh\.ru", r"Вам написали по вакансии|Сообщение от работодателя|вам написали из"),
    ("habr_applied", r"career\.habr\.com", r"Вы откликнулись на вакансию"),
]


def classify(sender: str, subject: str) -> str | None:
    for kind, frm, subj in KINDS:
        if re.search(frm, sender or "", re.I) and re.search(subj, subject or "", re.I):
            return kind
    return None


def _subject(msg) -> str:
    return str(make_header(decode_header(msg.get("Subject", ""))))


def _body(msg) -> str:
    plain = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/html", "text/plain") or part.get_filename():
            continue
        text = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/html":
            return text
        plain = plain or text
    return plain or ""


def parse_message(msg) -> dict:
    """-> {"kind", "day", "vacancies": [...], "events": [(url, title, company, status, source)]}."""
    sender, subj = str(make_header(decode_header(msg.get("From", "")))), _subject(msg)
    try:
        day = parsedate_to_datetime(msg.get("Date")).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        day = datetime.now().strftime("%Y-%m-%d")
    kind = classify(sender, subj)
    out = {"kind": kind, "day": day, "vacancies": [], "events": []}
    if kind is None:
        return out
    body = _body(msg)
    if kind == "hh_subscription":
        for vid, title, company, city, a, b in parse_hh_subscription(body):
            out["vacancies"].append(vacancy("hh", vid, title, company, f"https://hh.ru/vacancy/{vid}", day, a, b,
                                            "RUB", None, location=city,
                                            text="(подборка hh из почты: описание не загружается — сверка по названию)"))
    elif kind in ("hh_rejected", "hh_response"):
        r = parse_hh_vacancy_letter(body)
        if r:
            status = "rejected" if kind == "hh_rejected" else "viewed"
            out["events"].append((f"https://hh.ru/vacancy/{r[0]}", r[1], r[2], status, "hh"))
    elif kind == "habr_applied":
        r = parse_habr_applied(body, subj)
        if r:
            out["events"].append((r[0], r[1], r[2], "applied", "habr"))
    return out


def select_folder(imap, folder: str) -> str:
    """Открыть папку только на чтение. folder="ALL" — найти «Вся почта» по IMAP-флагу All (имя зависит от языка Gmail)."""
    name = folder
    if folder.upper() == "ALL":
        typ, lines = imap.list()
        for ln in lines or []:
            s = ln.decode(errors="replace") if isinstance(ln, bytes) else str(ln)
            if r"\All" in s:
                name = s.rsplit(' "/" ', 1)[-1].strip().strip('"')
                break
        else:
            name = "INBOX"
    typ, _ = imap.select(f'"{name}"', readonly=True)
    if typ != "OK":
        raise RuntimeError(f"папка {folder!r} не открылась")
    return name


def fetch(settings, days: int | None = None) -> dict:
    """Прочитать почту. -> {"vacancies", "events": [(url, title, company, status, source, day)], "stats"}."""
    cfg = settings.sources.mail
    user, pwd = settings.secret(cfg.user_env), settings.secret(cfg.password_env)
    if not (user and pwd):
        raise RuntimeError(f"нет {cfg.user_env}/{cfg.password_env} в workspace/.env — почта не читается")
    days = days or cfg.days
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    imap = imaplib.IMAP4_SSL(settings.secret("IMAP_SERVER") or cfg.server, 993, ssl_context=ssl.create_default_context(), timeout=60)
    vac, events, counts = {}, [], {}
    try:
        imap.login(user, pwd.replace(" ", ""))
        select_folder(imap, cfg.folder)
        uids = []
        for frm in ("noreply@hh.ru", "career.habr.com"):
            typ, data = imap.uid("SEARCH", None, "FROM", f'"{frm}"', "SINCE", since)
            uids += data[0].split() if typ == "OK" and data and data[0] else []
        for uid in uids:
            typ, parts = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if not raw:
                continue
            r = parse_message(email.message_from_bytes(raw))
            counts[r["kind"] or "other"] = counts.get(r["kind"] or "other", 0) + 1
            for v in r["vacancies"]:
                vac[v["id"]] = v
            events += [(*e, r["day"]) for e in r["events"]]
    finally:
        try:
            imap.logout()
        except Exception:       # noqa: BLE001
            pass
    names = {"hh_subscription": "подборок hh", "hh_rejected": "отказов", "hh_response": "ответов работодателей",
             "habr_applied": "откликов Хабра", "other": "прочих"}
    stats = f"писем за {days} дн.: " + ", ".join(f"{names.get(k, k)} {n}" for k, n in counts.items()) + \
            f"; вакансий из подборок {len(vac)}"
    return {"vacancies": list(vac.values()), "events": events, "stats": stats}
