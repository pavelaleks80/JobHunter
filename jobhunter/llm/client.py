"""
client.py — минимальный клиент chat/completions без SDK: один POST через requests.

Подходит любой OpenAI-совместимый сервер: OpenRouter, DeepSeek, OpenAI, Ollama (http://localhost:11434/v1),
корпоративные прокси. Ключ берётся из .env по имени переменной из config.yaml и нигде не логируется.
"""
from __future__ import annotations

import json
import re

import requests


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.1, timeout: int = 120,
                 verify=True):
        if not api_key:
            raise LLMError("нет ключа LLM: заполните LLM_API_KEY (и LLM_BASE_URL, LLM_MODEL) в workspace/.env")
        if not model:
            raise LLMError("не задана модель: LLM_MODEL в workspace/.env")
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model
        self.temperature, self.timeout, self.verify = temperature, timeout, verify

    @classmethod
    def from_settings(cls, settings, verify=True) -> LLMClient:
        c = settings.llm
        return cls(settings.secret(c.api_key_env), settings.secret(c.base_url_env, "https://openrouter.ai/api/v1"),
                   settings.secret(c.model_env), c.temperature, c.timeout, verify)

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        body = {"model": self.model, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                   "HTTP-Referer": "https://github.com/pavelaleks80/JobHunter", "X-Title": "JobHunter"}
        try:
            r = requests.post(f"{self.base_url}/chat/completions", json=body, headers=headers,
                              timeout=self.timeout, verify=self.verify)
        except requests.RequestException as e:
            raise LLMError(f"LLM недоступен: {e}") from e
        if r.status_code >= 400:
            raise LLMError(f"LLM {r.status_code}: {r.text[:300]}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"неожиданный ответ LLM: {r.text[:300]}") from e

    def chat_json(self, system: str, user: str) -> dict:
        """Ответ как JSON-объект; терпим обёртку ```json … ```."""
        text = self.chat(system, user, json_mode=True)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError(f"LLM не вернул JSON: {text[:200]}")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"битый JSON от LLM: {e}") from e
