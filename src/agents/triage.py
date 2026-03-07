"""Triage agent implementation for document profiling.

Contains logic for origin detection, layout complexity analysis,
strategy escalation, and domain hinting using a configurable rule set.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

import pdfplumber
import yaml

from src.models.profiles import DocumentProfile


LOG = logging.getLogger(__name__)


class BaseDomainClassifier(ABC):
    """Abstract interface for domain hint classifiers."""

    @abstractmethod
    def classify(self, text: str) -> str:
        """Return a domain hint string for the supplied text."""
        ...


class KeywordDomainClassifier(BaseDomainClassifier):
    """Concrete classifier that matches keywords from configuration."""

    def __init__(self, keywords: Dict[str, List[str]]) -> None:
        self.keywords = keywords

    def classify(self, text: str) -> str:
        lowered = text.lower()
        for domain, kwlist in self.keywords.items():
            for kw in kwlist:
                if kw in lowered:
                    return domain
        return "general"


class TriageAgent:
    """Agent responsible for profiling a corpus of PDF documents."""

    def __init__(self, config_path: Path | str = "rubric/extraction_rules.yaml"):
        self.config = self._load_config(config_path)
        self.domain_classifier = KeywordDomainClassifier(
            self.config.get("domain_keywords", {})
        )

    def _load_config(self, path: Path | str) -> dict:
        p = Path(path)
        if not p.exists():
            LOG.error("Config file %s not found", p)
            return {}
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def process_corpus(self, source_dir: Path = Path("data")) -> None:
        """Walk through ``source_dir`` and profile each PDF.

        Results are written as JSON files under ``.refinery/profiles``
        preserving the directory structure.
        """
        out_root = Path(".refinery/profiles")
        for pdf in source_dir.rglob("*.pdf"):
            try:
                profile = self.triage_pdf(pdf)
            except Exception:
                LOG.exception("failure profiling %s", pdf)
                continue
            rel = pdf.relative_to(source_dir)
            dest = out_root / rel.with_suffix(".json")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
            LOG.info("wrote profile %s", dest)

    def triage_pdf(self, path: Path) -> DocumentProfile:
        """Profile a single PDF file and return a DocumentProfile.

        Only the first ``triage_sampling_pages`` pages are loaded to avoid
        memory blow-ups on very large documents.
        """
        LOG.debug("triaging %s", path)
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            pdf = pdfplumber.open(path)
        except Exception as e:
            LOG.error("could not open pdf %s: %s", path, e)
            raise
        page_count = len(pdf.pages)
        if page_count == 0:
            LOG.error("empty PDF %s", path)
            # return a dummy profile with strategy C
            return DocumentProfile(
                origin_type="scanned_image",
                layout_complexity="mixed",
                domain_hint="general",
                suggested_strategy="C",
                metadata={
                    "char_density": 0.0,
                    "image_to_page_ratio": 0.0,
                    "font_count": 0,
                    "page_count": 0,
                    "file_size_mb": path.stat().st_size / (1024 * 1024),
                },
            )

        samples = int(self.config.get("triage_sampling_pages", 5))
        sample_pages = pdf.pages[:samples]

        # metrics
        total_chars = 0
        total_area = 0.0
        total_image_area = 0.0
        fonts = set()
        text_snippets: List[str] = []
        table_area = 0.0
        gutter_thresh = float(self.config.get("multi_column_gutter_threshold", 30.0))
        gutter_max = 0.0

        for page in sample_pages:
            area = float(page.width * page.height)
            total_area += area
            text = page.extract_text() or ""
            total_chars += len(text)
            text_snippets.append(text)
            # fonts
            for ch in getattr(page, "chars", []):
                fn = ch.get("fontname")
                if fn:
                    fonts.add(fn)
            # images
            for im in page.images or []:
                x0 = float(im.get("x0", im.get("x", 0.0)))
                x1 = float(im.get("x1", x0))
                y0 = float(im.get("y0", im.get("y", 0.0)))
                y1 = float(im.get("y1", y0))
                total_image_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
            # tables
            try:
                for tbl in page.find_tables():
                    bbox = tbl.bbox
                    table_area += (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            except Exception:
                pass
            # gutter heuristic: look at word bounding boxes
            words = page.extract_words()
            xs = sorted(set(float(w.get("x0", 0)) for w in words))
            for a, b in zip(xs, xs[1:]):
                gap = b - a
                gutter_max = max(gutter_max, gap)

        char_density = total_chars / total_area if total_area > 0 else 0.0
        image_ratio = total_image_area / total_area if total_area > 0 else 0.0
        font_count = len(fonts)
        file_mb = path.stat().st_size / (1024 * 1024)

        # origin detection
        scanned_thresh = float(self.config.get("scanned_density_threshold", 0.0001))
        mixed_thresh = float(self.config.get("mixed_density_threshold", 0.002))
        if char_density < scanned_thresh:
            origin = "scanned_image"
        elif char_density < mixed_thresh:
            origin = "mixed"
        else:
            origin = "native_digital"

        # layout complexity
        layout = "single_column"
        if gutter_max > gutter_thresh:
            layout = "multi_column"
        if table_area / total_area > float(self.config.get("table_area_ratio_threshold", 0.25)):
            layout = "table_heavy"
        # figure heavy detection omitted for brevity

        # domain hint
        full_text = "\n".join(text_snippets)
        domain = self.domain_classifier.classify(full_text)
        if domain not in ["financial", "legal", "technical", "government"]:
            domain = "general"

        # strategy escalation
        strategy = "B"
        if origin == "scanned_image":
            strategy = "C"
        elif origin == "native_digital" and layout == "single_column" and char_density > mixed_thresh:
            strategy = "A"
        elif origin == "mixed" or layout in ("multi_column", "table_heavy") or (
            mixed_thresh >= char_density >= scanned_thresh
        ):
            strategy = "B"
        # else default

        profile = DocumentProfile(
            origin_type=origin,
            layout_complexity=layout,
            domain_hint=domain,
            suggested_strategy=strategy,
            metadata={
                "char_density": char_density,
                "image_to_page_ratio": image_ratio,
                "font_count": font_count,
                "page_count": page_count,
                "file_size_mb": file_mb,
            },
        )
        return profile
