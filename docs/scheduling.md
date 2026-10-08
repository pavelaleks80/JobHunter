# Ежедневный запуск

## Windows — Планировщик заданий

В репозитории есть `scripts/run_daily.bat`. Откройте PowerShell **в папке репозитория** и выполните:

```powershell
$repo = (Get-Location).Path
$act  = New-ScheduledTaskAction -Execute "$repo\scripts\run_daily.bat" -WorkingDirectory $repo
$trg  = New-ScheduledTaskTrigger -Daily -At 9:00
$set  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "JobHunter" -Action $act -Trigger $trg -Settings $set
```

`-StartWhenAvailable` — если в 9:00 компьютер был выключен, задание выполнится при включении.
Проверить: `Start-ScheduledTask JobHunter`, затем посмотреть `workspace/logs/jobhunter.log`.

Если Python установлен не в PATH или используется виртуальное окружение — поправьте путь в `scripts/run_daily.bat`.

## Linux / macOS — cron

```bash
crontab -e
# каждый день в 9:00
0 9 * * * cd /path/to/JobHunter && .venv/bin/jobhunter run >> workspace/logs/cron.log 2>&1
```

## Docker

```bash
docker build -t jobhunter .
docker run --rm -v "$PWD/workspace:/app/workspace" jobhunter run
```

Профиль удобно построить так же: `docker run --rm -it -v "$PWD/workspace:/app/workspace" jobhunter profile`.
Расписание — cron хоста или любой планировщик контейнеров.

## Советы

- **Хабр и VPN.** Хабр Карьера обычно недоступна через VPN. Если VPN включён постоянно, getmatch и почта
  продолжат работать, а Хабр в письме будет помечен ⚠.
- **Отчёт открыт в Excel.** Если вчерашний отчёт открыт, отметки «Статус» из него соберутся при следующем запуске.
- **tracker.xlsx открыт.** Новый трекер сохранится рядом как `tracker_new.xlsx`.
