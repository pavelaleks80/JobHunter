"""
schema.py — структура workspace/profile.yaml.

Профиль — единственный источник правды о кандидате для сверки с требованиями. Его черновик строит LLM
из резюме (`jobhunter profile`), дальше файл правится руками. Поля:

  years        — стаж: default (лет) и уточнения по областям (match — регулярка по тексту требования);
  english      — уровень A1…C2 (или none);
  education    — уровень/направление для требований об образовании;
  skills       — что закрыто опытом («yes»): match — регулярка, evidence — чем именно подтверждено;
  partial      — закрыто частично (смежный опыт);
  hidden       — есть у кандидата, но в резюме не написано («gap» — подсказка дописать резюме);
  missing      — чего нет («no»); hard: true — специализации нет вовсе (критичный пробел).
Приоритет при нескольких совпадениях: missing > partial > hidden > skills > soft.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

LEVELS = ["none", "A1", "A2", "B1", "B2", "C1", "C2"]


class Rule(BaseModel):
    match: str
    note: str = ""
    hard: bool = False

    @field_validator("match")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        rx = re.compile(v, re.I)
        if rx.search("") is not None or rx.search("zzz qqq") is not None:
            raise ValueError(f"правило совпадает с любым текстом (пустая альтернатива?): {v!r}")
        return v


class YearsArea(BaseModel):
    match: str
    years: int


class Years(BaseModel):
    default: int = 0
    areas: list[YearsArea] = Field(default_factory=list)


class Education(BaseModel):
    level: str = ""            # «высшее», «среднее специальное»…
    field: str = ""            # «техническое», «экономическое», «ИТ»…
    match: str = ""            # регулярка направлений, которые считаем закрытыми: «информац|математ|техническ»
    note: str = ""


class Profile(BaseModel):
    name: str = ""
    headline: str = ""
    summary: str = ""          # 3–5 предложений о кандидате — используется ИИ-судьёй
    years: Years = Years()
    english: str = "none"
    education: Education = Education()
    skills: list[Rule] = Field(default_factory=list)
    partial: list[Rule] = Field(default_factory=list)
    hidden: list[Rule] = Field(default_factory=list)
    missing: list[Rule] = Field(default_factory=list)

    @field_validator("english")
    @classmethod
    def _level(cls, v: str) -> str:
        v = (v or "none").strip().upper()
        if v in ("NONE", "НЕТ", ""):
            return "none"
        if v not in LEVELS:
            raise ValueError(f"english: ожидается один из {LEVELS}, получено {v!r}")
        return v

    def english_rank(self) -> int:
        return LEVELS.index(self.english)


def load_profile(path: Path) -> Profile:
    if not path.exists():
        raise FileNotFoundError(f"нет профиля {path} — запустите `jobhunter profile` (или скопируйте jobhunter/examples/profile.example.yaml)")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Profile(**data)


def save_profile(profile: Profile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile.model_dump(), allow_unicode=True, sort_keys=False, width=120),
                    encoding="utf-8")
