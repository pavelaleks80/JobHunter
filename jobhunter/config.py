"""
config.py — загрузка workspace/config.yaml и workspace/.env в типизированный объект Settings.

Секреты (пароли, ключи API) живут только в .env и подставляются по именам переменных окружения,
указанным в config.yaml (поля *_env). В логах и отчётах они не появляются.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------- секции config.yaml
class RolePattern(BaseModel):
    pattern: str
    points: int = 25
    label: str = ""


class BoostGroup(BaseModel):
    pattern: str
    points: int = 5
    label: str = ""


class SalaryCfg(BaseModel):
    target: int = 300_000          # «хочу» — 20 баллов
    floor: int = 230_000           # «не ниже» — 15 баллов
    low: int = 200_000             # ниже — 0 баллов и предупреждение
    tax: float = 0.13              # пересчёт gross → net для сравнения вилок
    hidden_points: int = 10        # вилка не указана — нейтрально
    currency: str = "RUB"


class ScoringCfg(BaseModel):
    roles: list[RolePattern] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    boosts: list[BoostGroup] = Field(default_factory=list)
    boosts_cap: int = 30
    target_companies: list[str] = Field(default_factory=list)
    target_company_bonus: int = 10
    blacklist_companies: list[str] = Field(default_factory=list)   # подстроки: такие компании не показываем
    fresh_points: list[tuple[int, int]] = Field(default_factory=lambda: [(1, 10), (3, 7), (7, 4)])


class GetmatchCfg(BaseModel):
    enabled: bool = True
    queries: list[list[list[str]]] = Field(default_factory=lambda: [[["l", "moscow"], ["pa", "all"], ["sa", "any"]]])


class HabrCfg(BaseModel):
    enabled: bool = True
    queries: list[str] = Field(default_factory=list)
    location: str = "c_678"        # Москва в справочнике Хабр Карьеры
    pages: int = 2


class MailCfg(BaseModel):
    """Чтение почты по IMAP: подборки hh, отклики Хабра, отказы и приглашения hh."""
    enabled: bool = False
    server: str = "imap.gmail.com"
    folder: str = "INBOX"
    user_env: str = "IMAP_USER"
    password_env: str = "IMAP_PASSWORD"
    days: int = 7


class SourcesCfg(BaseModel):
    getmatch: GetmatchCfg = GetmatchCfg()
    habr: HabrCfg = HabrCfg()
    mail: MailCfg = MailCfg()


class EmailCfg(BaseModel):
    enabled: bool = True
    sender_name: str = "JobHunter"
    smtp_server_env: str = "SMTP_SERVER"
    smtp_port_env: str = "SMTP_PORT"
    login_env: str = "EMAIL_SENDER_LOGIN"
    password_env: str = "EMAIL_SENDER_PASSWORD"
    receiver_env: str = "JOBHUNTER_RECEIVER"
    top_n: int = 60
    top_n_mail_source: int = 30


class LLMCfg(BaseModel):
    api_key_env: str = "LLM_API_KEY"
    base_url_env: str = "LLM_BASE_URL"
    model_env: str = "LLM_MODEL"
    temperature: float = 0.1
    timeout: int = 120


class CoverCfg(BaseModel):
    """Сопроводительные письма (jobhunter cover)."""
    words: int = 170                   # примерная длина
    tone: str = "деловой, живой, без канцелярита и штампов"
    signature: str = ""                # подпись в конце (имя, телефон, Telegram); пусто — без подписи
    extra: str = ""                    # дополнительные пожелания к письму


class MatchingCfg(BaseModel):
    mode: Literal["rules", "llm", "hybrid"] = "rules"
    fit_ok: int = 75
    fit_partial: int = 50
    min_recognized: int = 3
    fuzzy_applied: float = 0.82


class Settings(BaseModel):
    workspace: Path
    resume_dir: str = "resume"
    profile_file: str = "profile.yaml"
    tracker_file: str = "tracker.xlsx"
    user_agent: str = "JobHunter/0.1 (+https://github.com/pavelaleks80/JobHunter)"
    http_timeout: int = 20
    scoring: ScoringCfg = ScoringCfg()
    salary: SalaryCfg = SalaryCfg()
    sources: SourcesCfg = SourcesCfg()
    email: EmailCfg = EmailCfg()
    llm: LLMCfg = LLMCfg()
    matching: MatchingCfg = MatchingCfg()
    cover: CoverCfg = CoverCfg()
    env: dict[str, str] = Field(default_factory=dict, exclude=True)

    # ------------------------------------------------------------ пути
    @property
    def data_dir(self) -> Path:
        return self.workspace / "data"

    @property
    def output_dir(self) -> Path:
        return self.workspace / "output"

    @property
    def log_dir(self) -> Path:
        return self.workspace / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.workspace / ".cache"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.db"

    @property
    def resume_path(self) -> Path:
        return self.workspace / self.resume_dir

    @property
    def covers_dir(self) -> Path:
        return self.workspace / "covers"

    @property
    def profile_path(self) -> Path:
        return self.workspace / self.profile_file

    @property
    def tracker_path(self) -> Path:
        return self.workspace / self.tracker_file

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.output_dir, self.log_dir, self.cache_dir, self.resume_path, self.covers_dir):
            d.mkdir(parents=True, exist_ok=True)

    def secret(self, env_name: str, default: str = "") -> str:
        """Значение из .env / окружения по имени переменной. Никогда не логировать."""
        return self.env.get(env_name) or os.environ.get(env_name, default)


# ---------------------------------------------------------------- загрузка
def load_env(path: Path) -> dict[str, str]:
    """Простой парсер .env (KEY=VALUE, # — комментарий). Значения не выводятся."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def default_workspace() -> Path:
    return Path(os.environ.get("JOBHUNTER_WORKSPACE", Path.cwd() / "workspace")).resolve()


def load_settings(workspace: Path | None = None) -> Settings:
    ws = (workspace or default_workspace()).resolve()
    cfg_path = ws / "config.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    raw = raw or {}
    raw["workspace"] = ws
    s = Settings(**raw)
    s.env = load_env(ws / ".env")
    return s
