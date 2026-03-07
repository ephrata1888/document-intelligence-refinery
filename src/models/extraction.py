from pydantic import BaseModel
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from enum import Enum
from docling_core.types.doc import DocItem as PageContent, ProvenanceItem as ProvenanceChain
if TYPE_CHECKING:
    from .provenance import ProvenanceChain
class Strategy(Enum):
    A = "fast_text"
    B = "layout"
    C = "vision"

class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    page_index: int

class TableData(BaseModel):
    headers: List[str]
    rows: List[List[Any]]
    caption: Optional[str] = None
    bbox: Optional[BoundingBox] = None

class PageContent(BaseModel):
    text: str
    tables: List[TableData]
    page_confidence: float
    text_bbox: Optional[BoundingBox] = None
    provenance: Optional[List['ProvenanceChain']] = None  # Will be added

class NormalizedDocument(BaseModel):
    doc_id: str
    strategy_used: Strategy
    confidence_score: float
    processing_time: float  # in seconds
    estimated_cost: float  # in USD
    pages: List[PageContent]

PageContent.model_rebuild()
ProvenanceChain.model_rebuild()