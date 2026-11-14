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


def test_main_without_companies_as_script(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_json(workdir / "data" / "companies.json", [])
    runpy.run_module("run", run_name="__main__")
    assert "crawled 0 companies, failed 0 [], open jobs 0" in capsys.readouterr().out
