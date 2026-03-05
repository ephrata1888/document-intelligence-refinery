import logging
from pathlib import Path
from typing import List

import pdfplumber
import pytest

from src.agents.triage import KeywordDomainClassifier, TriageAgent
from src.models.profiles import DocumentProfile


class DummyPage:
    def __init__(self, text: str, width: float = 600, height: float = 800, fonts: List[str] = None):
        self._text = text
        self.width = width
        self.height = height
        self.images = []
        self._fonts = fonts or []

    def extract_text(self):
        return self._text

    @property
    def chars(self):
        return [{"fontname": f} for f in self._fonts]

    def find_tables(self):
        return []

    def extract_words(self):
        # simulate word bboxes if needed; here empty by default
        return []


class DummyPDF:
    def __init__(self, pages: List[DummyPage]):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture(autouse=True)
def caplog_setup(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


def test_keyword_domain_classifier():
    cls = KeywordDomainClassifier({
        "financial": ["annual report", "balance sheet"],
        "legal": ["decree"],
    })
    assert cls.classify("This is an annual report for 2020") == "financial"
    assert cls.classify("No keywords here") == "general"


def test_zero_density_strategy_c(monkeypatch, tmp_path, caplog):
    # create a dummy pdf with one page that has no text and no fonts
    pdf_obj = DummyPDF([DummyPage("", fonts=[])])

    monkeypatch.setattr(pdfplumber, "open", lambda p: pdf_obj)
    agent = TriageAgent()
    (tmp_path / "dummy.pdf").touch()
    profile = agent.triage_pdf(tmp_path / "dummy.pdf")
    assert profile.suggested_strategy == "C"
    assert profile.origin_type == "scanned_image"


def test_high_density_table_strategy_b(monkeypatch, tmp_path):
    # page with lots of text and a large table area
    page = DummyPage("x" * 10000, fonts=["Times"])
    # patch find_tables to return a table with big bbox
    class Table:
        bbox = (0, 0, 600, 400)

    page.find_tables = lambda: [Table()]
    pdf_obj = DummyPDF([page])
    monkeypatch.setattr(pdfplumber, "open", lambda p: pdf_obj)
    agent = TriageAgent()
    (tmp_path / "dummy2.pdf").touch()
    profile = agent.triage_pdf(tmp_path / "dummy2.pdf")
    assert profile.suggested_strategy == "B"
    assert profile.layout_complexity == "table_heavy"


def test_empty_pdf_logs_error(monkeypatch, tmp_path, caplog):
    pdf_obj = DummyPDF([])
    monkeypatch.setattr(pdfplumber, "open", lambda p: pdf_obj)
    agent = TriageAgent()
    (tmp_path / "empty.pdf").touch()
    profile = agent.triage_pdf(tmp_path / "empty.pdf")
    assert profile.suggested_strategy == "C"
    assert "empty PDF" in caplog.text
