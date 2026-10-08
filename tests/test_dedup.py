from jobhunter import dedup


def _v(source, vid, title, company, **kw):
    v = {"source": source, "id": vid, "title": title, "company": company, "url": f"https://{source}/{vid}",
         "score": 50, "is_new": True, "applied": "", "sal_from": None, "sal_to": None, "gross": None}
    v.update(kw)
    return v


def test_merge_across_sources():
    rows = [_v("hh", "1", "Руководитель проектов (Москва)", "МТС Банк. Головной офис", sal_from=300000, is_new=False),
            _v("habr", "2", "Руководитель проектов", "МТС Банк"),
            _v("getmatch", "3", "Product Owner", "МТС Банк"),                 # другое название — не дубль
            _v("hh", "4", "Руководитель проектов", "Ромашка")]                 # другая компания — не дубль
    out, n = dedup.merge(rows)
    assert n == 1 and len(out) == 3
    main = next(v for v in out if v["id"] == "2")
    assert [d["id"] for d in main["dups"]] == ["1"]
    assert main["sal_from"] == 300000                                         # вилка подтянулась из hh
    assert main["is_new"] is False                                            # копию уже видели
    assert dedup.also_text(main, {"hh": "hh (почта)"}) == "hh (почта)"


def test_applied_on_copy_marks_main():
    rows = [_v("habr", "2", "Delivery Manager", "Тест"), _v("hh", "1", "Delivery manager", "Тест", applied="rejected")]
    out, _ = dedup.merge(rows)
    assert out[0]["source"] == "habr" and out[0]["applied"] == "rejected"


def test_same_source_not_merged():
    out, n = dedup.merge([_v("hh", "1", "РП", "Тест"), _v("hh", "2", "РП", "Тест")])
    assert n == 0 and len(out) == 2


def test_same_company():
    assert dedup.same_company("мтс", "мтс головной офис")
    assert not dedup.same_company("мтс", "мтсбанк")
    assert not dedup.same_company("", "мтс")
