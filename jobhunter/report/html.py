"""
html.py — тело письма: все подходящие вакансии без отклика (🆕 — новые), блок подборки hh, воронка, источники.
"""
from __future__ import annotations

from collections import Counter
from html import escape

from .common import salary_text, why_only

_STYLE = """<style>
body{font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;font-size:14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:6px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
th{background:#f4f6f8}.s{font-weight:bold;text-align:center}.mut{color:#888;font-size:12px}
.err{color:#c0392b}.ok{color:#0a8f3c}.v0{background:#e8f6ec}.v1{background:#fff7e0}
</style>"""


def build_html(rows, status, run_dt, top_n=60, top_n_mail=30, funnel=None):
    from . import SRC_NAME, VERDICT_ORDER
    active = [v for v in rows if not v.get("applied")]
    site = [v for v in active if v["source"] != "hh"]
    fit = [v for v in site if v["match"]["verdict"] in ("Подходит", "Частично")]
    fit.sort(key=lambda v: (VERDICT_ORDER[v["match"]["verdict"]], -(v["match"]["fit"] or 0), -v["score"]))
    n_new = sum(1 for v in fit if v["is_new"])
    cnt = Counter(v["match"]["verdict"] for v in site)
    h = [f"<html><head>{_STYLE}</head><body>",
         f"<h3>Подходящих вакансий без вашего отклика: {len(fit)} (новых: {n_new})</h3>",
         f"<div class='mut'>Без отклика всего {len(site)}: подходит {cnt.get('Подходит', 0)}, частично "
         f"{cnt.get('Частично', 0)}, проверь вручную {cnt.get('Проверь вручную', 0)}, не подходит "
         f"{cnt.get('Не подходит', 0)} (две последние группы — только в Excel). «Соотв.» — доля обязательных "
         f"требований, закрытых опытом из профиля. 🆕 — появилась с прошлого запуска. Отметить отклик: колонка "
         f"«Статус» в Excel. Запуск {run_dt:%d.%m.%Y %H:%M}.</div><br>"]
    top = fit[:top_n]
    if top:
        h.append("<table><tr><th>Соотв.</th><th>Вакансия</th><th>Зарплата</th><th>Не хватает / дописать в резюме</th></tr>")
        for v in top:
            m = v["match"]
            miss = why_only(m["miss"]) + [f"частично: {x}" for x in why_only(m["partial"])]
            notes = "<br>".join(escape(x) for x in dict.fromkeys(miss)) or "—"
            if "НИЖЕ ПОЛА" in v["why"]:
                notes = "<b>⚠ зарплата ниже вашего пола</b><br>" + notes
            gap = why_only(m["gap"])
            if gap:
                notes += "<br><b>Дописать в резюме:</b> " + escape("; ".join(dict.fromkeys(gap)))
            cls = "v0" if m["verdict"] == "Подходит" else "v1"
            badge = "<b>🆕</b> " if v["is_new"] else ""
            h.append(f"<tr class='{cls}'><td class='s'>{m['fit']}%<br><span class='mut'>{m['verdict']}</span></td>"
                     f"<td>{badge}<a href='{escape(v['url'])}'>{escape(v['title'])}</a><br>{escape(v['company'])}<br>"
                     f"<span class='mut'>{SRC_NAME.get(v['source'])} · {escape(v['published'])} · балл {v['score']}</span></td>"
                     f"<td>{escape(salary_text(v))}</td><td class='mut'>{notes}</td></tr>")
        h.append("</table>")
        if len(fit) > len(top):
            h.append(f"<p class='mut'>…и ещё {len(fit) - len(top)} — в Excel, лист «К отклику».</p>")
    else:
        h.append("<p>Подходящих вакансий без отклика нет.</p>")

    hh_all = [v for v in active if v["source"] == "hh" and v["match"]["verdict"] != "Не подходит"]
    hh_all.sort(key=lambda x: (not x["is_new"], -x["score"]))
    if hh_all:
        h.append(f"<h4>hh.ru из вашей подписки — {len(hh_all)} без отклика (новых: "
                 f"{sum(1 for v in hh_all if v['is_new'])})</h4><div class='mut'>Описание не загружается (API hh для "
                 f"соискателей закрыто), поэтому отбор только по названию.</div><table>")
        for v in hh_all[:top_n_mail]:
            badge = "<b>🆕</b> " if v["is_new"] else ""
            h.append(f"<tr><td class='s'>{v['score']}</td><td>{badge}<a href='{escape(v['url'])}'>{escape(v['title'])}</a>"
                     f"<br><span class='mut'>{escape(v['company'])} · {escape(v['published'])} · "
                     f"{escape(salary_text(v))}</span></td></tr>")
        h.append("</table>")

    if funnel and funnel["total"]:
        b = funnel["by_status"]
        h.append(f"<h4>Воронка</h4><p>Откликов {funnel['total']}: ответили {b.get('viewed', 0)}, приглашений "
                 f"{b.get('invited', 0)}, офферов {b.get('offer', 0)}, отказов {b.get('rejected', 0)}"
                 + (f"; медиана ответа {funnel['median_wait']} дн." if funnel["median_wait"] is not None else "")
                 + f". Без ответа 7+ дней: {len(funnel['silent_7d'])}.</p>")

    h.append("<h4>Источники</h4><ul>")
    for k, (ok, msg) in status.items():
        h.append(f"<li><b>{SRC_NAME.get(k, k)}</b>: <span class='{'ok' if ok else 'err'}'>"
                 f"{'OK' if ok else 'ошибка'}</span> — {escape(msg)}</li>")
    h.append("</ul><p class='mut'>JobHunter · github.com/pavelaleks80/JobHunter</p></body></html>")
    return "\n".join(h), (len(fit), n_new)
