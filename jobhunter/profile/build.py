"""
build.py — черновик profile.yaml из текста резюме с помощью LLM.

Модель получает текст резюме и описание структуры профиля, возвращает JSON. Мы валидируем его схемой
(битые регулярки отбрасываются с предупреждением) и сохраняем в workspace/profile.yaml.
Без LLM: `template()` создаёт заготовку, которую заполняют руками.
"""
from __future__ import annotations

from .schema import Education, Profile, Rule, Years, YearsArea

SYSTEM = """Ты — карьерный консультант. По тексту резюме составь профиль кандидата для автоматической сверки
с требованиями вакансий. Отвечай ТОЛЬКО JSON-объектом указанной структуры, на русском языке.

Структура:
{
 "name": "имя", "headline": "желаемая должность", "summary": "3-5 предложений: кто кандидат, ключевой опыт и цифры",
 "years": {"default": <общий профильный стаж, лет>, "areas": [{"match": "<регулярка по тексту требования>", "years": <лет>}]},
 "english": "none|A1|A2|B1|B2|C1|C2",
 "education": {"level": "высшее|...", "field": "направление", "match": "<регулярка направлений, которые закрыты>", "note": ""},
 "skills":  [{"match": "<регулярка>", "note": "<чем подтверждено в резюме: факт, цифра, проект>"}],
 "partial": [{"match": "<регулярка>", "note": "<почему частично>"}],
 "hidden":  [{"match": "<регулярка>", "note": "<что есть, но не написано в резюме>"}],
 "missing": [{"match": "<регулярка>", "note": "<чего нет>", "hard": true|false}]
}

Правила:
- match — регулярное выражение Python в нижнем регистре, без ё (пиши «е»), с альтернативами через |
  и усечёнными корнями: "управлени\\w* проект|руководств\\w* проект|project manag". Никогда не оставляй пустых
  альтернатив ("a||b") и не пиши пустых match.
- skills: 25-45 правил по всему, что есть в резюме: домены, методологии, инструменты, роли, типы заказчиков,
  достижения. Чем точнее note, тем полезнее отчёт.
- missing: 8-15 типичных для целевой роли требований, которых у кандидата явно нет (другие специализации,
  языки программирования, отрасли). hard=true — если это целая специализация (например, ML, мобильная разработка).
- hidden: что обычно есть у такого специалиста, но в резюме не упомянуто — оставь пустым, если не уверен.
- years.areas: уточни стаж по областям, где он меньше общего (например, продуктовые роли отдельно от проектных).
"""


def template() -> Profile:
    return Profile(
        name="Имя Фамилия", headline="Руководитель проектов",
        summary="Кратко о кандидате: опыт, домены, ключевые достижения.",
        years=Years(default=10, areas=[YearsArea(match=r"продакт|product|продукт", years=5)]),
        english="B1",
        education=Education(level="высшее", field="техническое", match=r"техническ|информац|информатик|математ"),
        skills=[Rule(match=r"jira|confluence", note="Jira, Confluence — ежедневно"),
                Rule(match=r"agile|scrum|kanban", note="Scrum/Kanban в команде 20+")],
        partial=[Rule(match=r"\bsql\b", note="SQL на уровне простых запросов")],
        hidden=[Rule(match=r"python", note="Python для личных проектов — в резюме нет")],
        missing=[Rule(match=r"\bml\b|machine learning|машинн\w* обучени", note="нет опыта ML", hard=True)],
    )


def build_from_text(client, resume_text: str, log=print) -> Profile:
    data = client.chat_json(SYSTEM, f"Резюме:\n\n{resume_text[:30000]}")
    return _coerce(data, log)


def _coerce(data: dict, log) -> Profile:
    """Собрать Profile, отбрасывая битые правила вместо падения целиком."""
    clean = {k: data.get(k) for k in ("name", "headline", "summary", "english") if data.get(k)}
    y = data.get("years") or {}
    areas = []
    for a in y.get("areas") or []:
        try:
            areas.append(YearsArea(**a))
        except Exception as e:      # noqa: BLE001
            log(f"  пропущено years.areas {a}: {e}")
    clean["years"] = Years(default=int(y.get("default") or 0), areas=areas)
    try:
        clean["education"] = Education(**(data.get("education") or {}))
    except Exception as e:          # noqa: BLE001
        log(f"  education не разобрано: {e}")
    for key in ("skills", "partial", "hidden", "missing"):
        rules = []
        for r in data.get(key) or []:
            try:
                rules.append(Rule(**r))
            except Exception as e:  # noqa: BLE001
                log(f"  пропущено {key} {r}: {e}")
        clean[key] = rules
    return Profile(**clean)
