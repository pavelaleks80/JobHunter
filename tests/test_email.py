from jobhunter.notify import email as mailer


class FakeSMTP:
    logins = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, pwd):
        FakeSMTP.logins.append((user, pwd))

    def sendmail(self, frm, to, msg):
        assert "JobHunter" in msg


def test_app_password_spaces_removed(settings, monkeypatch):
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    settings.env = {"EMAIL_SENDER_LOGIN": "bot@gmail.com", "EMAIL_SENDER_PASSWORD": "abcd efgh ijkl mnop",
                    "SMTP_SERVER": "smtp.gmail.com", "JOBHUNTER_RECEIVER": "me@gmail.com"}
    ok, msg = mailer.send(settings, "Тема", "<p>ok</p>")
    assert ok and FakeSMTP.logins[-1] == ("bot@gmail.com", "abcdefghijklmnop")
    assert (settings.log_dir / "last_email.html").exists()


def test_no_password(settings):
    settings.env = {"EMAIL_SENDER_LOGIN": "bot@gmail.com"}
    ok, msg = mailer.send(settings, "Тема", "<p>ok</p>")
    assert not ok and "EMAIL_SENDER_PASSWORD" in msg
