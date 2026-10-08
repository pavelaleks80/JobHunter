"""matching — сверка требований вакансии с профилем кандидата (правила из profile.yaml и/или ИИ-судья)."""
from .engine import Matcher
from .requirements import extract

__all__ = ["Matcher", "extract"]
