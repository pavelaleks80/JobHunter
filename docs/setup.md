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

### Windows: «"jobhunter" не является внутренней или внешней командой»

Пакет установлен, но Windows не находит программу `jobhunter.exe`. Так бывает, если Python ставили новым
установщиком с python.org (Python Install Manager) или через Anaconda без добавления в PATH: `pip` кладёт
`jobhunter.exe` в папку `Scripts` выбранного Python, а её нет в PATH.

**Самый простой выход** — запускать через Python, это работает всегда:

```bash
python -m jobhunter check
python -m jobhunter run --no-email
```

Любую команду из документации можно писать так: вместо `jobhunter …` — `python -m jobhunter …`.

**Если хочется писать просто `jobhunter`**, добавьте папку `Scripts` в PATH:

1. Узнайте путь к ней:
   ```bash
   python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
   ```
   Например: `C:\Users\<имя>\AppData\Local\Python\pythoncore-3.14-64\Scripts`.
2. «Пуск» → наберите «переменные среды» → **«Изменение переменных среды текущего пользователя»** →
   строка `Path` → **«Изменить»** → **«Создать»** → вставьте путь → OK.
3. Откройте **новое** окно командной строки — в старом PATH не обновится.

Если используете виртуальное окружение (`.venv`), достаточно его активировать (`.venv\Scripts\activate`) —
тогда `jobhunter` находится без правки PATH.

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
| `EMAIL_SENDER_LOGIN`, `EMAIL_SENDER_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT` | отправить отчёт | [пароль приложения](app-passwords.md) — пошагово для Gmail, Mail.ru, Яндекса |
| `JOBHUNTER_RECEIVER` | кому слать отчёт | ваш адрес |
| `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_SERVER` | читать письма hh и Хабра | [пароль приложения](app-passwords.md) |

Обычный пароль от почты не подойдёт — нужен **пароль приложения**: [docs/app-passwords.md](app-passwords.md).

Профиль строится один раз — это несколько центов на OpenRouter. Пароли приложений безопаснее обычного пароля:
их можно отозвать, не меняя основной.

## 4. Профиль

```bash
jobhunter profile
```

Подробно о формате и о том, как править правила, — [profile.md](profile.md). Без LLM: `jobhunter profile --template`
создаёт заготовку, которую заполняют руками (образец — [`jobhunter/examples/profile.example.yaml`](https://github.com/pavelaleks80/JobHunter/blob/main/jobhunter/examples/profile.example.yaml)).

## 5. Что искать — `workspace/config.yaml`

### Как читать запись вида `sources.mail.enabled`

В документации параметры называются **путём через точку**. Такой строки в `config.yaml` нет — точка означает
«раздел внутри раздела». В файле вложенность задаётся **отступами** (два пробела на уровень):

| В документации | В `config.yaml` |
|---|---|
| `sources.mail.enabled: true` | раздел `sources:` → внутри него `mail:` → внутри него `enabled: true` |

```yaml
sources:                 # уровень 1, без отступа
  getmatch:
    enabled: true
  habr:
    enabled: true
  mail:                  # уровень 2 — два пробела
    enabled: true        # уровень 3 — четыре пробела: это и есть sources.mail.enabled
    folder: ALL          # sources.mail.folder
    days: 7              # sources.mail.days
```

Ещё примеры: `salary.target` — строка `target:` в разделе `salary:`; `matching.mode` — строка `mode:` в разделе
`matching:`; `scoring.blacklist_companies` — строка `blacklist_companies:` в разделе `scoring:`.

Правила правки:

- меняйте только значение после двоеточия, отступы не трогайте — от них зависит, к какому разделу относится строка;
- отступы — **пробелами**, не табуляцией;
- текст после `#` — комментарий, его можно не трогать;
- после правки запустите `python -m jobhunter check` (или `jobhunter check`) — если файл испорчен, он скажет об ошибке.

### Главные параметры

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
- **Письмо не отправляется.** `jobhunter check` покажет, какой переменной не хватает; нужен пароль
  приложения, а не пароль от ящика — см. [app-passwords.md](app-passwords.md), раздел «Если что-то не так».
