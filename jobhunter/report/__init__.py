"""report — Excel-отчёт и HTML-письмо."""
from .excel import write_excel
from .html import build_html

VERDICT_ORDER = {"Подходит": 0, "Частично": 1, "Проверь вручную": 2, "Не подходит": 3}
SRC_NAME = {"getmatch": "getmatch", "habr": "Хабр", "hh": "hh (почта)"}

__all__ = ["write_excel", "build_html", "VERDICT_ORDER", "SRC_NAME"]
