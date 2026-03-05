from __future__ import annotations

from pathlib import Path
from typing import Dict, Literal

from pydantic import BaseModel, Field


class DocumentProfile(BaseModel):
    """Data model capturing profiling results for a document.

    All fields are mandatory according to Phase 1 requirements.
    """

    origin_type: Literal["native_digital", "scanned_image", "mixed"]
    layout_complexity: Literal[
        "single_column",
        "multi_column",
        "table_heavy",
        "figure_heavy",
        "mixed",
    ]
    domain_hint: Literal[
        "financial",
        "legal",
        "technical",
        "government",
        "general",
    ]
    suggested_strategy: Literal["A", "B", "C"]
    metadata: Dict[str, float]

    class Config:
        validate_assignment = True
        frozen = True
