# Установка и настройка

## 1. Установка

Нужен Python 3.11 или новее.

```bash
git clone https://github.com/pavelaleks80/JobHunter.git
cd JobHunter
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e .
```

Проверка: `jobhunter --help`.

## 2. Рабочая папка

```bash
jobhunter init
```

Создаётся `workspace/` (в git не попадает):

```
workspace/
├── config.yaml      что искать: роли, исключения, ключевые слова, зарплата, источники
├── .env             секреты: почта, ключ LLM
├── resume/          сюда — резюме (.pdf, .docx, .txt, .md); берётся самый свежий файл
├── profile.yaml     профиль кандидата (создаёт `jobhunter profile`)
├── tracker.xlsx     воронка откликов (пересоздаётся из базы при каждом запуске)
├── data/jobs.db     база: вакансии, описания, отклики
├── output/          отчёты Вакансии_ДДММГГ.xlsx
└── logs/            журнал и копия последнего письма
```

Другую папку можно задать ключом `--workspace` или переменной окружения `JOBHUNTER_WORKSPACE`.

## 3. Секреты — `workspace/.env`

| Переменная | Зачем | Где взять |
|---|---|---|
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | построить профиль из резюме; ИИ-судья | [OpenRouter](https://openrouter.ai/keys), [DeepSeek](https://platform.deepseek.com), OpenAI или любой OpenAI-совместимый сервер |
| `EMAIL_SENDER_LOGIN`, `EMAIL_SENDER_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT` | отправить отчёт | Mail.ru / Яндекс: «пароль для внешних приложений»; Gmail: пароль приложения |
| `JOBHUNTER_RECEIVER` | кому слать отчёт | ваш адрес |
| `IMAP_USER`, `IMAP_PASSWORD` | читать письма hh и Хабра | Gmail: myaccount.google.com → Безопасность → Пароли приложений |

Профиль строится один раз — это несколько центов на OpenRouter. Пароли приложений безопаснее обычного пароля:
их можно отозвать, не меняя основной.

## 4. Профиль

```bash
jobhunter profile
```

Подробно о формате и о том, как править правила, — [profile.md](profile.md). Без LLM: `jobhunter profile --template`
создаёт заготовку, которую заполняют руками (образец — [`jobhunter/examples/profile.example.yaml`](https://github.com/pavelaleks80/JobHunter/blob/main/jobhunter/examples/profile.example.yaml)).

## 5. Что искать — `workspace/config.yaml`

Главное:

- `scoring.roles` — регулярные выражения по названию вакансии. Вакансия без совпадения отбрасывается.
- `scoring.exclude` — что отбрасывать всегда (junior, стажёр…).
- `scoring.boosts` — ключевые слова, которые поднимают вакансию в списке (домены, технологии).
- `salary` — цель, пол и нижняя граница **на руки**; вилки «до вычета» пересчитываются по `tax`.
- `sources` — параметры getmatch и Хабра, включение почты.

Шаблоны пишутся в нижнем регистре, «ё» заменяется на «е». Проверить шаблон удобно на
[regex101.com](https://regex101.com) (вкус Python).

## 6. Проверка и первый запуск

```bash
jobhunter check
jobhunter run --no-email
```

Откройте `workspace/output/Вакансии_*.xlsx` и посмотрите листы «К отклику» и «Пробелы резюме». Если вердикты
выглядят странно — поправьте `profile.yaml` (см. [profile.md](profile.md)) и запустите ещё раз: описания
вакансий кэшируются, второй запуск быстрый.

## Частые проблемы

- **Хабр Карьера: «не отвечает».** Сайт часто недоступен через VPN — запускайте без него.
- **`[X509] PEM lib`.** Битый блок в certifi; JobHunter сам собирает очищенный бандл в `workspace/.cache`.
- **Письмо не отправляется.** `jobhunter check` покажет, какой переменной не хватает; для Mail.ru нужен пароль
  для внешних приложений, а не пароль от ящика.
