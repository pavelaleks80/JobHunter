"""
requirements.py — вырезать из описания вакансии список требований.

На входе HTML описания (getmatch / Хабр / hh). На выходе два списка строк:
  must — обязательные требования (блок «Требования», «Мы ждём», «Что ищем в кандидатах» ...);
  nice — «будет плюсом».
Если заголовка требований нет, берём пункты списков, похожие на требования («опыт», «знание», «понимание»...).
"""
import html as _html
import re

# Заголовки, с которых начинается блок требований
REQ_HEAD = re.compile(r"требовани|ожидани|ожидаем|мы жд[её]м|ждем от|что (мы )?ищем|ищем в кандидат|идеальн\w* кандидат|"
                      r"что важно|нам важно|для нас важно|ты нам подходишь|вы нам подходите|кого мы ищем|"
                      r"тебе (точно )?(к нам|подойд)|нам подойд|наш кандидат|о тебе|о вас|requirements|what we expect|"
                      r"you have|необходим\w* (навык|опыт)|квалификац|что нужно знать|что потребуется|твой опыт|ваш опыт", re.I)
NICE_HEAD = re.compile(r"будет плюсом|плюсом будет|преимуществ|nice to have|будет здорово|желательно|бонусом", re.I)
# Любой «другой» заголовок закрывает блок
OTHER_HEAD = re.compile(r"услови|предлага|обязанност|задач|чем (предстоит|будешь|будете)|что (предстоит|нужно будет|ты будешь|вы будете)|"
                        r"делать|бенефит|льгот|о компании|о команде|о проекте|почему|мы —|формат|график|"
                        r"здоровь|развити|обучени|offer|benefits|responsibilities|what you.?ll do|стек", re.I)

_HEAD_RE = re.compile(r"<(h\d|strong|b)[^>]*>(.*?)</\1>", re.I | re.S)
_LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_REQ_WORDS = re.compile(r"^(опыт|знание|понимание|умение|навык|владение|высшее|английск|готовность|способность|"
                        r"experience|knowledge|опыт работы)", re.I)


def _txt(s):
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", s or ""))).strip(" .;,-–—• ")


def _items(chunk):
    """Пункты блока: <li> или строки текста."""
    lis = [_txt(x) for x in _LI_RE.findall(chunk)]
    if lis:
        return [x for x in lis if len(x) > 3]
    lines = re.split(r"<br\s*/?>|\n|<p[^>]*>|•|·|;", chunk)
    return [t for t in (_txt(x) for x in lines) if len(t) > 8]


def extract(desc_html):
    """-> (must, nice). Пустые списки, если описания нет."""
    if not desc_html:
        return [], []
    # Режем текст по заголовкам: [(заголовок, содержимое до следующего заголовка)]
    heads = list(_HEAD_RE.finditer(desc_html))
    must, nice = [], []
    for i, m in enumerate(heads):
        title = _txt(m.group(2)).lower()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(desc_html)
        body = desc_html[m.end():end]
        if len(title) > 90:
            continue
        if NICE_HEAD.search(title):
            nice += _items(body)
        elif REQ_HEAD.search(title) and not OTHER_HEAD.search(title.replace("требования", "")):
            # внутри блока требований может быть строка «Будет плюсом: ...»
            for it in _items(body):
                (nice if NICE_HEAD.search(it[:40]) else must).append(it)
    if not must:
        # Заголовков нет — берём пункты, начинающиеся с «опыт / знание / понимание ...»
        must = [x for x in _items(desc_html) if _REQ_WORDS.search(x)]
    # внутри одного пункта иногда «Будет плюсом: X» в конце — отрезаем;
    # пункты с пометкой «(будет преимуществом)», «приветствуется» — это не обязательные требования
    clean = []
    for x in must:
        parts = re.split(r"(?i)\.?\s*(?:будет плюсом|плюсом будет):?", x)
        head = parts[0].strip()
        if len(parts) > 1 and parts[1].strip():
            nice.append(parts[1].strip())
        if _NICE_MARK.search(head):
            nice.append(head)
        elif head:
            clean.append(head)
    return clean, nice


_NICE_MARK = re.compile(r"будет преимуществ|большое преимуществ|большой плюс|как преимуществ|приветствуется|желательн|nice to have|is a plus", re.I)
