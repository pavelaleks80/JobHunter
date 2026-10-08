"""
net.py — HTTP-сессия с «чистым» бандлом сертификатов.

Зачем: в некоторых сборках certifi (в частности, после добавления сертификатов Минцифры) встречаются пустые
PEM-блоки, из-за которых любой HTTPS-запрос падает с «[X509] PEM lib». Здесь берём certifi, выкидываем
битые блоки и кладём копию в workspace/.cache. Системный файл не трогаем.
"""
from __future__ import annotations

import re
import ssl
from pathlib import Path

import certifi
import requests

_PEM_RE = re.compile(r"-----BEGIN CERTIFICATE-----\s*[A-Za-z0-9+/=\s]+?-----END CERTIFICATE-----")


def ca_bundle_path(cache_dir: Path) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / "ca_bundle.pem"
    text = Path(certifi.where()).read_text(encoding="utf-8", errors="ignore")
    good = [b for b in _PEM_RE.findall(text) if len(b) > 200]
    body = "\n".join(good) + "\n"
    if not out.exists() or out.read_text(encoding="utf-8") != body:
        out.write_text(body, encoding="utf-8")
    ssl.create_default_context(cafile=str(out))      # проверка: файл читается OpenSSL
    return str(out)


def session(cache_dir: Path, user_agent: str) -> requests.Session:
    s = requests.Session()
    s.verify = ca_bundle_path(cache_dir)
    s.headers["User-Agent"] = user_agent
    return s


def get_json(s: requests.Session, url: str, params=None, headers=None, retries: int = 2, timeout: int = 20):
    """GET с повтором: сеть через VPN бывает капризной."""
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            r = s.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:      # noqa: BLE001 — любую ошибку отдаём наверх после повторов
            last = e
    assert last is not None
    raise last
