from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from models.provenance import ProvenanceChain


class QueryState(BaseModel):
    """State for the LangGraph query agent pipeline."""

    question: str
    query_type: Optional[str] = None
    context_chunks: List[str] = []
    selected_sections: List[str] = []
    answer: Optional[str] = None
    provenance_chain: List[ProvenanceChain] = []

    class Config:
        validate_assignment = True