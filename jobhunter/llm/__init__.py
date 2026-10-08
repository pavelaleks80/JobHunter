"""llm — клиент OpenAI-совместимого chat/completions API (OpenRouter, DeepSeek, OpenAI, Ollama, прокси)."""
from .client import LLMClient, LLMError

__all__ = ["LLMClient", "LLMError"]
