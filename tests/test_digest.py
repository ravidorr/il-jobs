import runpy
import sqlite3
import sys
from pathlib import Path

import pytest

import digest
from tests.conftest import add_job


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
