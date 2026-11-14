import runpy
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import browser_crawl
import run
from tests.conftest import add_job, write_json


def job(job_id: str, title: str = "T") -> dict[str, str]:
    return {"job_id": job_id, "title": title, "location": "L", "url": "u", "team": "t", "posted": "p"}


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fake 'fake' ATS: results[slug] is a list of outcomes, popped per call (last one repeats)."""
    results: dict[str, list[Any]] = {}

    def fetch(slug: str) -> Any:
        outcomes = results[slug]
        return outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]

    monkeypatch.setitem(run.ADAPTERS, "fake", fetch)
    monkeypatch.setattr(run.time, "sleep", lambda _s: None)
    return results


def co(name: str, ats: str = "fake", slug: str | None = None, status: str = "ok") -> dict[str, str]:
    return {"name": name, "ats": ats, "slug": slug or name.lower(), "status": status}


def test_init_is_idempotent(workdir: Path) -> None:
    run.init().close()
    conn = run.init()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(crawl_log)")]
    assert "note" in cols
    conn.close()


def test_crawl_retries_once(adapter: dict[str, Any]) -> None:
    adapter["a"] = [None, [job("1")]]
    assert run.crawl(co("A")) == (co("A"), [job("1")])
    adapter["b"] = [[job("1")]]
    assert run.crawl(co("B"))[1] == [job("1")]
    adapter["c"] = [None]
    assert run.crawl(co("C"))[1] is None


def test_main_full_cycle(
    workdir: Path, adapter: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = run.init()
    add_job(conn, "Known", "old", "Old job")
    add_job(conn, "Known", "gone", "Gone job")
    add_job(conn, "Br2", "b2old", "Browser old")
    add_job(conn, "Br1", "x", "Anything", status="closed")
    conn.close()
    companies = [
        co("New"),
        co("Known"),
        co("Failing"),
        co("Skipped", status="ats_failed"),
        co("Br1", ats="browser", slug="https://br1"),
        co("Br2", ats="browser", slug="https://br2"),
        co("Br3", ats="browser", slug="https://br3"),
        co("Br4", ats="browser", slug="https://br4"),
        co("Br5", ats="browser", slug="https://br5"),
    ]
    write_json(workdir / "data" / "companies.json", companies)
    adapter["new"] = [[job("n1"), job("n2")]]
    adapter["known"] = [[job("old", "Renamed"), job("fresh")]]
    adapter["failing"] = [None]
    crawled = {
        "https://br1": [job("b1")],
        "https://br2": [],
        "https://br3": [],
        "https://br4": None,
    }
    monkeypatch.setattr(run, "crawl_many", lambda urls: {u: crawled[u] for u in urls if u in crawled})
    monkeypatch.setitem(browser_crawl.WHY, "https://br3", "empty page")
    monkeypatch.setitem(browser_crawl.WHY, "https://br4", "blocked")
    run.main()
    out = capsys.readouterr().out
    assert "failed 4 ['Failing', 'Br2', 'Br4', 'Br5']" in out
    assert "browser Br1" in out
    assert "<- empty page" in out
    assert "FAILED  <- blocked" in out

    check = sqlite3.connect(run.DB)
    rows = {(r[0], r[1]): r[2:] for r in check.execute("SELECT company,job_id,status,reported,title FROM jobs")}
    assert rows[("New", "n1")] == ("open", 1, "T")  # baseline: silently reported
    assert rows[("Known", "fresh")][:2] == ("open", 0)  # new job at known company: unreported
    assert rows[("Known", "old")] == ("open", 0, "Renamed")
    assert rows[("Known", "gone")][0] == "closed"
    assert rows[("Br2", "b2old")][0] == "open"  # empty browser result with history is not trusted
    assert rows[("Br1", "x")][0] == "closed"
    notes = dict(check.execute("SELECT company, note FROM crawl_log"))
    assert notes["Failing"] == "request failed"
    assert notes["Br3"] == "empty page"
    assert notes["Br2"] == "request failed"
    assert notes["Br5"] == "request failed"
    assert notes["New"] == ""
    check.close()


def test_main_israel_only_keeps_israel_jobs(workdir: Path, adapter: dict[str, Any]) -> None:
    conn = run.init()
    add_job(conn, "Big", "old-us", "Old US job", location="Austin, TX")
    add_job(conn, "Big", "old-il", "Old IL job", location="Tel Aviv, Israel")
    conn.close()
    write_json(workdir / "data" / "companies.json", [{**co("Big"), "israel_only": True}, co("Plain")])
    il = {**job("new-il"), "location": "Haifa, IL"}
    us = {**job("new-us"), "location": "Chicago, IL"}
    nowhere = {**job("no-loc"), "location": None}
    adapter["big"] = [[{**job("old-il"), "location": "Tel Aviv, Israel"}, il, us, nowhere]]
    adapter["plain"] = [[{**job("p1"), "location": "Austin, TX"}]]
    run.main()
    check = sqlite3.connect(run.DB)
    rows = {(r[0], r[1]): r[2] for r in check.execute("SELECT company,job_id,status FROM jobs")}
    assert rows[("Big", "old-il")] == "open"
    assert rows[("Big", "new-il")] == "open"
    assert ("Big", "new-us") not in rows  # not stored
    assert ("Big", "no-loc") not in rows
    assert rows[("Big", "old-us")] == "closed"  # was stored before the flag: closes
    assert rows[("Plain", "p1")] == "open"  # no flag: kept whatever the location
    logged = dict(check.execute("SELECT company, n_jobs FROM crawl_log"))
    assert logged["Big"] == 2 + 0
    check.close()


def seed_open(conn: sqlite3.Connection, name: str, count: int, **kw: Any) -> None:
    for i in range(count):
        add_job(conn, name, f"j{i}", f"Job {i}", **kw)


def log_runs(conn: sqlite3.Connection, name: str, notes: list[str | None]) -> None:
    """Earlier crawl log rows, oldest first."""
    for day, note in enumerate(notes, start=1):
        conn.execute(
            "INSERT INTO crawl_log(ts,company,ats,ok,n_jobs,note) VALUES(?,?,?,?,?,?)",
            (f"2024-01-{day:02d}T00:00:00", name, "browser", 0, 0, note),
        )


def crawl_browser(workdir: Path, monkeypatch: pytest.MonkeyPatch, company: dict[str, Any], jobs: list[Any]) -> None:
    write_json(workdir / "data" / "companies.json", [company])
    monkeypatch.setattr(run, "crawl_many", lambda urls: dict.fromkeys(urls, jobs))
    monkeypatch.setitem(browser_crawl.WHY, company["slug"], "")
    browser_crawl.WHY.pop(company["slug"])
    run.main()


def open_jobs(name: str) -> int:
    check = sqlite3.connect(run.DB)
    count: int = check.execute("SELECT COUNT(*) FROM jobs WHERE company=? AND status='open'", (name,)).fetchone()[0]
    check.close()
    return count


def last_log(name: str) -> tuple[int, int, str]:
    check = sqlite3.connect(run.DB)
    row: tuple[int, int, str] = check.execute(
        "SELECT ok, n_jobs, note FROM crawl_log WHERE company=? ORDER BY ts DESC LIMIT 1", (name,)
    ).fetchone()
    check.close()
    return row


BIG = co("Big", ats="browser", slug="https://big")
OPEN = 20
ISRAEL_OPEN = 12
API_KEPT = 2
DROP_NOTE = "sharp drop: got 5, 20 open before"


def test_sharp_drop_keeps_jobs_open_and_says_why(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = run.init()
    seed_open(conn, "Big", 20)
    conn.commit()
    conn.close()
    crawl_browser(workdir, monkeypatch, BIG, [job(f"j{i}") for i in range(5)])
    assert open_jobs("Big") == OPEN  # nothing closed
    assert last_log("Big") == (0, 0, DROP_NOTE)  # logged as a failed crawl, with the reason
    out = capsys.readouterr().out
    assert "failed 1 ['Big']" in out
    assert f"FAILED  <- {DROP_NOTE}" in out


@pytest.mark.parametrize(
    ("returned", "open_after"),
    [(9, 20), (10, 10)],  # under half is held, exactly half is believed
)
def test_sharp_drop_is_under_half(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, returned: int, open_after: int
) -> None:
    conn = run.init()
    seed_open(conn, "Big", 20)
    conn.commit()
    conn.close()
    crawl_browser(workdir, monkeypatch, BIG, [job(f"j{i}") for i in range(returned)])
    assert open_jobs("Big") == open_after


@pytest.mark.parametrize(
    ("open_before", "open_after"), [(run.DROP_MIN_OPEN - 1, 1), (run.DROP_MIN_OPEN, run.DROP_MIN_OPEN)]
)
def test_small_companies_are_not_judged_on_a_drop(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, open_before: int, open_after: int
) -> None:
    conn = run.init()
    seed_open(conn, "Big", open_before)
    conn.commit()
    conn.close()
    crawl_browser(workdir, monkeypatch, BIG, [job("j0")])
    assert open_jobs("Big") == open_after


@pytest.mark.parametrize(
    ("earlier", "open_after"),
    [
        ([DROP_NOTE] * 2, 20),  # held twice: held again
        ([DROP_NOTE] * 3, 5),  # held three runs in a row: the drop is real
        ([DROP_NOTE, "", DROP_NOTE], 20),  # a run in between that was not held restarts the count
        ([DROP_NOTE, None, DROP_NOTE], 20),  # a log row with no note counts as not held
        (["", DROP_NOTE, DROP_NOTE, DROP_NOTE], 5),  # only the latest runs matter
    ],
)
def test_a_sharp_drop_is_believed_after_three_held_runs(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, earlier: list[str | None], open_after: int
) -> None:
    conn = run.init()
    seed_open(conn, "Big", 20)
    log_runs(conn, "Big", earlier)
    conn.commit()
    conn.close()
    crawl_browser(workdir, monkeypatch, BIG, [job(f"j{i}") for i in range(5)])
    assert open_jobs("Big") == open_after


def test_sharp_drop_counts_israel_jobs_for_an_israel_only_company(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = run.init()
    seed_open(conn, "Big", 12, location="Tel Aviv, Israel")
    conn.commit()
    conn.close()
    israel = [{**job(f"j{i}"), "location": "Haifa, Israel"} for i in range(3)]
    abroad = [{**job(f"a{i}"), "location": "Austin, TX"} for i in range(100)]
    crawl_browser(workdir, monkeypatch, {**BIG, "israel_only": True}, israel + abroad)
    assert open_jobs("Big") == ISRAEL_OPEN  # 103 jobs came back, but only 3 are Israel jobs and 12 were open
    assert last_log("Big")[2] == "sharp drop: got 3, 12 open before"


def test_a_drop_in_an_api_company_is_still_believed(workdir: Path, adapter: dict[str, Any]) -> None:
    conn = run.init()
    seed_open(conn, "Api", 20)
    conn.commit()
    conn.close()
    write_json(workdir / "data" / "companies.json", [co("Api")])
    adapter["api"] = [[job("j0"), job("j1")]]
    run.main()
    assert open_jobs("Api") == API_KEPT  # API feeds are complete lists: only browser crawls are held back


def test_main_without_companies_as_script(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_json(workdir / "data" / "companies.json", [])
    runpy.run_module("run", run_name="__main__")
    assert "crawled 0 companies, failed 0 [], open jobs 0" in capsys.readouterr().out
