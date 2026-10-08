"""email.py — отправка отчёта по SMTP (465/SSL, при неудаче 587/STARTTLS). Копия HTML — logs/last_email.html."""
from __future__ import annotations

import smtplib
import ssl
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr


def send(settings, subject: str, html: str, attach_path=None):
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    (settings.log_dir / "last_email.html").write_text(html, encoding="utf-8")
    c = settings.email
    server = settings.secret(c.smtp_server_env, "smtp.mail.ru")
    port = int(settings.secret(c.smtp_port_env, "465") or 465)
    login = settings.secret(c.login_env)
    pwd = settings.secret(c.password_env).replace(" ", "")   # пароль приложения Google показывается группами через пробел
    to = settings.secret(c.receiver_env) or login
    if not (login and pwd):
        return False, f"нет {c.login_env}/{c.password_env} в workspace/.env — письмо не отправлено"
    msg = MIMEMultipart()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = formataddr((str(Header(c.sender_name, "utf-8")), login))
    msg.attach(MIMEText(html, "html", "utf-8"))
    if attach_path:
        part = MIMEApplication(attach_path.read_bytes(), Name=attach_path.name)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", attach_path.name))
        msg.attach(part)
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(server, port, context=ctx, timeout=30) as s:
            s.login(login, pwd)
            s.sendmail(login, [to], msg.as_string())
        return True, f"отправлено на {to}"
    except Exception as e_ssl:      # noqa: BLE001
        try:
            with smtplib.SMTP(server, 587, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(login, pwd)
                s.sendmail(login, [to], msg.as_string())
            return True, f"отправлено на {to} (587)"
        except Exception as e_tls:  # noqa: BLE001
            return False, f"SMTP недоступен: {port} — {e_ssl}; 587 — {e_tls}"
