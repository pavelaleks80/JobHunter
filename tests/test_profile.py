import zipfile

import pytest

from jobhunter.profile import build
from jobhunter.profile.extract_text import extract, find_resume
from jobhunter.profile.schema import load_profile, save_profile

TEXT = "Руководитель проектов. " * 30


def _docx(path, paragraphs):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {w}><w:body>{body}</w:body></w:document>')


def test_txt_cp1251(tmp_path):
    f = tmp_path / "cv.txt"
    f.write_bytes(TEXT.encode("cp1251"))
    assert extract(f).startswith("Руководитель проектов")


def test_docx(tmp_path):
    f = tmp_path / "cv.docx"
    _docx(f, ["Анна Смирнова", "Руководитель ИТ-проектов", TEXT])
    t = extract(f)
    assert "Анна Смирнова" in t and "Руководитель ИТ-проектов" in t


def test_too_short(tmp_path):
    f = tmp_path / "scan.txt"
    f.write_text("скан", encoding="utf-8")
    with pytest.raises(ValueError):
        extract(f)


def test_find_resume_latest(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_resume(tmp_path)
    (tmp_path / "old.txt").write_text(TEXT, encoding="utf-8")
    (tmp_path / "~$lock.docx").write_text("x", encoding="utf-8")
    (tmp_path / "photo.jpg").write_text("x", encoding="utf-8")
    assert find_resume(tmp_path).name == "old.txt"


class FakeLLM:
    model = "fake"

    def __init__(self, data):
        self.data = data

    def chat_json(self, system, user):
        assert "Резюме" in user
        return self.data


def test_build_drops_bad_rules(tmp_path):
    data = {"name": "Анна", "headline": "РП", "summary": "Опыт", "english": "b1",
            "years": {"default": 10, "areas": [{"match": "product", "years": 2}]},
            "education": {"level": "высшее", "field": "тех", "match": "техническ"},
            "skills": [{"match": "jira", "note": "Jira"}, {"match": "a||b", "note": "битое"}, {"match": "[", "note": "битое"}],
            "missing": [{"match": "\\bml\\b", "note": "нет ML", "hard": True}]}
    logs = []
    p = build.build_from_text(FakeLLM(data), TEXT, log=logs.append)
    assert [r.note for r in p.skills] == ["Jira"] and len(logs) == 2
    assert p.english == "B1" and p.missing[0].hard
    save_profile(p, tmp_path / "profile.yaml")
    assert load_profile(tmp_path / "profile.yaml") == p


def test_template_is_valid(tmp_path):
    save_profile(build.template(), tmp_path / "p.yaml")
    assert load_profile(tmp_path / "p.yaml").skills
