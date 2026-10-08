import sqlite3

from jobhunter.matching import judge
from jobhunter.profile.schema import load_profile


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def chat_json(self, system, user):
        self.calls += 1
        return {"items": [{"i": 1, "v": "yes", "why": "проектный офис"}, {"i": 2, "v": "no", "why": "нет"},
                          {"i": 9, "v": "yes"}, {"i": 3, "v": "maybe"}]}


def test_judge_caches_and_applies(settings, matcher):
    con = sqlite3.connect(":memory:")
    prof = load_profile(settings.profile_path)
    reqs = ["Опыт работы с Tableau", "Знание Bitrix24 изнутри", "Опыт работы с Power BI"]
    llm = FakeLLM()
    v = judge.judge(llm, con, prof, reqs)
    assert v[reqs[0]][0] == "yes" and v[reqs[1]][0] == "no" and reqs[2] not in v
    judge.judge(llm, con, prof, reqs[:2])
    assert llm.calls == 1                                                      # второй раз — из кэша
    base = matcher.match(["Опыт управления проектами", "Jira"] + reqs)
    res = judge.apply(base, v, matcher)
    assert res["recognized"] == base["recognized"] + 2
    assert any("ИИ:" in x for x in res["have"])
