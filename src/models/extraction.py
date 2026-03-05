from pydantic import BaseModel
from typing import List, Dict
from enum import Enum

class Strategy(Enum):
    A = "fast_text"
    B = "layout"
    C = "vision"

class PageContent(BaseModel):
    text: str
    tables: List[Dict]
    page_confidence: float

class NormalizedDocument(BaseModel):
    doc_id: str
    strategy_used: Strategy
    confidence_score: float
    processing_time: float  # in seconds
    estimated_cost: float  # in USD
    pages: List[PageContent]