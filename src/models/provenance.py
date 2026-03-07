from pydantic import BaseModel, Field
from typing import List

class ProvenanceChain(BaseModel):
    """Tracks the origin of extracted content for auditability."""
    
    document_name: str = Field(..., description="Name of the source document")
    page_no: int = Field(..., description="Page number where content was extracted")
    bbox: List[float] = Field(..., description="Bounding box coordinates [x0, y0, x1, y1]")
    content_hash: str = Field(..., description="SHA256 hash of the content for verification")

ProvenanceChain.model_rebuild()