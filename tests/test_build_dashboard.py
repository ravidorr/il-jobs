import json
import re
import runpy
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import build_dashboard
from tests.conftest import add_job, write_json


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("HTTP 403, title='x'", "its site blocks automated access from GitHub's servers"),
        ("blocked page", "its site blocks automated access from GitHub's servers"),
        ("x" * 200, "x" * 120),
        ("", "the last crawl failed"),
        (None, "the last crawl failed"),
    ],
)
def test_reason(note: str | None, expected: str) -> None:
    assert build_dashboard.reason(note) == expected


def log(conn: sqlite3.Connection, ts: str, company: str, ok: int, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO crawl_log(ts,company,ats,ok,n_jobs,note) VALUES(?,?,?,?,?,?)", (ts, company, "x", ok, 0, note)
    )
    conn.commit()


def write_css(workdir: Path) -> None:
    (workdir / "design-system" / "components").mkdir(parents=True)
    (workdir / "design-system" / "tokens.css").write_text(":root{--a:1}\n", encoding="utf-8")
    (workdir / "design-system" / "components" / "b.css").write_text(".b{}\n", encoding="utf-8")
    (workdir / "design-system" / "components" / "a.css").write_text(".a{}\n", encoding="utf-8")
    (workdir / "templates" / "dashboard.css").write_text("body{}\n", encoding="utf-8")


def prepare(workdir: Path) -> None:
    write_json(workdir / "data" / "companies.json", [{"name": "Zed", "status": "ok"}, {"name": "Alpha", "status": "x"}])
    (workdir / "templates" / "dashboard.html").write_text("<script>var D=__DATA__;</script>", encoding="utf-8")


def read_payload(workdir: Path) -> Any:
    html = (workdir / "docs" / "index.html").read_text(encoding="utf-8")
    raw = html.removeprefix("<script>var D=").removesuffix(";</script>").replace("<\\/", "</")
    return json.loads(raw)


def test_main_builds_dashboard(db: sqlite3.Connection, workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    prepare(workdir)
    log(db, "2024-01-01", "Down", 1)
    log(db, "2024-01-02", "Down", 0, "HTTP 403")
    log(db, "2024-01-03", "Down", 0, None)
    log(db, "2024-01-01", "Flaky", 1)
    log(db, "2024-01-02", "Flaky", 0, "oops")
    log(db, "2024-01-01", "Never", 0, "x")
    log(db, "2024-01-02", "Never", 0, "x")
    add_job(db, "Acme", "1", "Product Manager </b>")
    add_job(db, "Acme", "2", "Product Intern", first_seen="2024-02-01")
    add_job(db, "Acme", "3", "Student", location=None, first_seen=None, team=None)
    add_job(db, "Acme", "4", "Accountant", location="London " + "y" * 100)
    add_job(db, "Acme", "5", "Closed Product", status="closed")
    add_job(db, "Down", "6", "Junior Dev")
    db.close()
    build_dashboard.main()
    payload = read_payload(workdir)
    gaps = payload["gaps"]
    assert gaps["untracked"] == ["Alpha"]
    assert [g["c"] for g in gaps["blocked"]] == ["Down", "Never"]
    assert gaps["blocked"][0]["last"] == "2024-01-01"
    assert gaps["blocked"][0]["why"].startswith("the last crawl failed")
    assert gaps["blocked"][1]["last"] == "never"
    jobs = {j["i"]: j for j in payload["jobs"]}
    assert sorted(jobs) == ["1", "2", "3", "4", "6"]
    assert jobs["1"]["k"] == "pm"
    assert jobs["2"]["k"] == "pm"
    assert jobs["3"]["k"] == "junior"
    assert jobs["4"]["k"] == "other"
    assert jobs["1"]["il"] is True
    assert jobs["3"]["il"] is False
    assert jobs["3"]["f"] == ""
    assert len(jobs["4"]["l"]) == len("London " + "y" * 100) - 27
    assert jobs["1"]["n"] is False
    assert jobs["2"]["n"] is True
    assert jobs["6"]["s"] is True
    assert "failing" in capsys.readouterr().out


def test_old_schema_without_note_column_runs_as_script(workdir: Path) -> None:
    prepare(workdir)
    conn = sqlite3.connect(build_dashboard.DB)
    conn.executescript(
        """
        CREATE TABLE jobs(company, job_id, title, team, location, url, first_seen, status);
        CREATE TABLE crawl_log(ts, company, ats, ok, n_jobs);
        INSERT INTO crawl_log VALUES('2024-01-01','Old','x',0,0);
        INSERT INTO crawl_log VALUES('2024-01-02','Old','x',0,0);
        """
    )
    conn.commit()
    conn.close()
    runpy.run_module("build_dashboard", run_name="__main__")
    payload = read_payload(workdir)
    assert payload["gaps"]["blocked"] == [{"c": "Old", "why": "the last crawl failed", "last": "never"}]
    assert payload["jobs"] == []


def test_read_css_inlines_sources_in_order(workdir: Path) -> None:
    write_css(workdir)
    assert build_dashboard.read_css() == ":root{--a:1}\n.a{}\n.b{}\nbody{}"


def test_job_posting() -> None:
    job = {"c": "Acme", "t": "PM", "u": "https://x.test/1", "l": "Tel Aviv", "f": "2024-01-02", "il": True}
    posting = build_dashboard.job_posting(job)
    assert posting["title"] == "PM"
    assert posting["hiringOrganization"]["name"] == "Acme"
    assert posting["datePosted"] == "2024-01-02"
    assert posting["jobLocation"]["address"] == {
        "@type": "PostalAddress",
        "addressLocality": "Tel Aviv",
        "addressCountry": "IL",
    }
    abroad = build_dashboard.job_posting({**job, "f": "", "il": False})
    assert "datePosted" not in abroad
    assert "addressCountry" not in abroad["jobLocation"]["address"]


def test_page_gets_css_and_json_ld(db: sqlite3.Connection, workdir: Path) -> None:
    write_css(workdir)
    write_json(workdir / "data" / "companies.json", [])
    (workdir / "templates" / "dashboard.html").write_text(
        "<style>__CSS__</style><script>__JSONLD__</script><script>__DATA__</script>", encoding="utf-8"
    )
    add_job(db, "Acme", "1", "Product Manager __CSS__ </script>")
    add_job(db, "Acme", "2", "Accountant", location="London")
    db.close()
    build_dashboard.main()
    html = (workdir / "docs" / "index.html").read_text(encoding="utf-8")
    css, ld, data = re.fullmatch(r"<style>(.*)</style><script>(.*)</script><script>(.*)</script>", html, re.S).groups()  # type: ignore[union-attr]
    assert css.endswith("body{}")
    listing = json.loads(ld.replace("<\\/", "</"))
    assert [i["item"]["title"] for i in listing["itemListElement"]] == ["Product Manager __CSS__ </script>"]
    assert listing["itemListElement"][0]["position"] == 1
    assert "__CSS__" in json.loads(data.replace("<\\/", "</"))["jobs"][0]["t"]
