import runpy
import sqlite3
import sys
from pathlib import Path

import pytest

import digest
from common import DROP_BELIEVED, DROP_NOTE
from tests.conftest import add_crawls, add_job


def test_select_filters(db: sqlite3.Connection) -> None:
    add_job(db, "A", "1", "Product Manager")
    add_job(db, "A", "2", "Product Manager", location="London")
    add_job(db, "A", "3", "Accountant")
    add_job(db, "A", "4", "Senior Product Manager")
    add_job(db, "A", "5", "Junior Software Engineer")
    add_job(db, "A", "6", "Product Intern", reported=1)
    add_job(db, "A", "7", "Product Designer", status="closed")
    add_job(db, "B", "8", "Student", location=None)
    assert [j["title"] for j in digest.select(db)] == ["Junior Software Engineer", "Product Manager"]
    everything = digest.select(db, only_unreported=False)
    assert [j["title"] for j in everything] == ["Junior Software Engineer", "Product Intern", "Product Manager"]
    assert [j["pm"] for j in everything] == [False, True, True]


def test_render_groups_and_escapes() -> None:
    jobs = [
        {"company": "A&B", "title": "PM <1>", "location": "TLV", "url": "http://u?a=1&b=2", "pm": True},
        {"company": "C", "title": "Intern", "location": None, "url": None, "pm": False},
    ]
    subject, body = digest.render(jobs)
    assert subject.startswith("New Israel jobs: 2 (")
    assert "<h3>Product roles (1)</h3>" in body
    assert "<h3>Student / junior / intern (non-product titles)</h3>" not in body
    assert "Student / junior / intern (non-product titles) (1)" in body
    assert "A&amp;B" in body
    assert "PM &lt;1&gt;" in body
    assert 'href=""' in body
    assert "No new matching jobs" not in body


def test_render_empty() -> None:
    subject, body = digest.render([])
    assert subject.startswith("New Israel jobs: 0")
    assert "<p>No new matching jobs today.</p>" in body
    assert "<h3>" not in body


def test_main_preview_then_commit(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_job(db, "A", "1", "Product Manager")
    add_job(db, "A", "2", "Intern")
    db.close()
    monkeypatch.setattr(sys, "argv", ["digest.py"])
    digest.main()
    out = capsys.readouterr().out
    assert "PM  A" in out
    assert "marked reported" not in out
    assert "Product Manager" in Path("data/digest.html").read_text()
    check = sqlite3.connect(digest.DB)
    assert check.execute("SELECT COUNT(*) FROM jobs WHERE reported=1").fetchone()[0] == 0
    monkeypatch.setattr(sys, "argv", ["digest.py", "--commit"])
    runpy.run_module("digest", run_name="__main__")
    assert "marked reported" in capsys.readouterr().out
    assert check.execute("SELECT COUNT(*) FROM jobs WHERE reported=0").fetchone()[0] == 0


HELD = f"{DROP_NOTE}: got 0, 20 open before"
BELIEVED = f"{DROP_BELIEVED}: got 0, 5 open before"
FAIL = "HTTP 403, title='Access Denied'"


def gap_by_company(db: sqlite3.Connection) -> dict[str, dict[str, object]]:
    return {g["company"]: g for g in digest.coverage_gaps(db)}


def test_coverage_gaps_ignore_healthy_and_one_off_failures(db: sqlite3.Connection) -> None:
    add_crawls(db, "Healthy", [(1, ""), (1, "")])
    add_crawls(db, "OneOff", [(1, ""), (0, FAIL)])  # failed once, as the dashboard also lets pass
    add_crawls(db, "Recovered", [(0, FAIL), (0, FAIL), (1, "")])
    assert digest.coverage_gaps(db) == []


@pytest.mark.parametrize(
    ("rows", "new"),
    [
        ([(1, ""), (1, ""), (0, FAIL), (0, FAIL)], True),  # the second failure in a row: it just started failing
        ([(1, ""), (0, FAIL), (0, FAIL), (0, FAIL)], False),  # already failing yesterday
        ([(0, FAIL), (0, FAIL)], True),  # never crawled well, and too little history to say it was failing before
        ([(0, FAIL)], True),
    ],
)
def test_a_failing_company_is_a_new_gap_only_when_it_just_started(
    db: sqlite3.Connection, rows: list[tuple[int, str | None]], new: bool
) -> None:
    add_crawls(db, "Blocked", rows)
    gap = gap_by_company(db)["Blocked"]
    assert (gap["kind"], gap["note"], gap["new"]) == ("failing", FAIL, new)


def test_last_good_is_the_last_successful_day_or_never(db: sqlite3.Connection) -> None:
    add_crawls(db, "Was", [(1, ""), (1, ""), (0, FAIL), (0, FAIL)])
    add_crawls(db, "Never", [(0, FAIL), (0, FAIL)])
    gaps = gap_by_company(db)
    assert gaps["Was"]["last_good"] == "2026-01-02"
    assert gaps["Never"]["last_good"] == "never"


@pytest.mark.parametrize(
    ("rows", "new"),
    [
        ([(1, ""), (0, HELD)], True),  # first held crawl
        ([(0, HELD)], True),  # a single row of history
        ([(1, ""), (0, HELD), (0, HELD)], False),  # held yesterday too
    ],
)
def test_a_held_crawl_is_its_own_kind_and_new_on_its_first_day(
    db: sqlite3.Connection, rows: list[tuple[int, str | None]], new: bool
) -> None:
    add_crawls(db, "Big", rows)
    gap = gap_by_company(db)["Big"]
    assert (gap["kind"], gap["note"], gap["new"]) == ("held", HELD, new)


def test_a_believed_drop_is_a_new_gap_once_and_even_though_the_crawl_succeeded(db: sqlite3.Connection) -> None:
    add_crawls(db, "Small", [(0, HELD)] * 3 + [(1, BELIEVED)])
    gap = gap_by_company(db)["Small"]
    assert (gap["kind"], gap["new"], gap["note"]) == ("closed", True, BELIEVED)
    add_crawls(db, "Small2", [(0, HELD)] * 3 + [(1, BELIEVED), (1, "")])
    assert "Small2" not in gap_by_company(db)  # the next day it is an ordinary company with no jobs


def test_a_null_note_counts_as_no_note(db: sqlite3.Connection) -> None:
    add_crawls(db, "Quiet", [(0, None), (0, None)])
    assert gap_by_company(db)["Quiet"]["note"] == ""


def test_coverage_gaps_without_a_crawl_log_or_a_note_column() -> None:
    bare = sqlite3.connect(":memory:")
    assert digest.coverage_gaps(bare) == []  # no crawl_log table at all
    bare.execute("CREATE TABLE crawl_log(ts TEXT, company TEXT, ats TEXT, ok INTEGER, n_jobs INTEGER)")
    bare.executemany(
        "INSERT INTO crawl_log VALUES(?,?,?,?,?)",
        [("2026-01-01T06:00:00", "Old", "browser", 0, 0), ("2026-01-02T06:00:00", "Old", "browser", 0, 0)],
    )
    (gap,) = digest.coverage_gaps(bare)  # a database from before the note column
    assert (gap["company"], gap["kind"], gap["note"]) == ("Old", "failing", "")


def gap(company: str, kind: str, note: str, new: bool = True, last_good: str = "2026-01-02") -> dict[str, object]:
    return {"company": company, "kind": kind, "note": note, "new": new, "last_good": last_good}


def test_render_lists_the_gaps_under_the_jobs() -> None:
    jobs = [{"company": "A", "title": "PM", "location": "TLV", "url": "http://u", "pm": True}]
    gaps = [
        gap("Blocked & Co", "failing", FAIL),
        gap("Held", "held", HELD, new=False),
        gap("Gone", "closed", BELIEVED),
        gap("Silent", "failing", "", new=False, last_good="never"),
        gap("Long", "failing", "x" * 300),
    ]
    subject, body = digest.render(jobs, gaps)
    assert subject.startswith("New Israel jobs: 1 (")  # the gaps do not change the subject when there are jobs
    assert "<h3>Not crawled properly (5)</h3>" in body
    assert "<b>Blocked &amp; Co</b> <b>new</b>: not crawled: HTTP 403, title=&#x27;Access Denied&#x27; " in body
    assert "<b>Held</b>: crawl held, nothing closed: " in body  # not new: no tag
    assert "<b>Gone</b> <b>new</b>: all its jobs were closed after an empty crawl: " in body
    assert "<b>Silent</b>: not crawled <i>(last good crawl never)</i>" in body  # no note: no colon
    assert "x" * digest.GAP_NOTE_MAX in body
    assert "x" * (digest.GAP_NOTE_MAX + 1) not in body
    assert body.index("Product roles") < body.index("Not crawled properly")


def test_render_subject_is_an_alert_when_only_a_gap_is_new() -> None:
    subject, body = digest.render([], [gap("Blocked", "failing", FAIL), gap("Held", "held", HELD)])
    assert subject.startswith("Job crawl alert: 2 new (")
    assert "No new matching jobs today." in body
    quiet, _ = digest.render([], [gap("Blocked", "failing", FAIL, new=False)])
    assert quiet.startswith("New Israel jobs: 0")  # an old gap alone is not news


def test_main_preview_prints_the_gaps(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_crawls(db, "Blocked", [(1, ""), (0, FAIL), (0, FAIL)])
    add_crawls(db, "Held", [(0, HELD), (0, HELD)])
    monkeypatch.setattr(sys, "argv", ["digest.py"])
    digest.main()
    out = capsys.readouterr().out
    assert "GAP new Blocked" in out
    assert "GAP     Held" in out
    assert "Not crawled properly (2)" in Path("data/digest.html").read_text()
