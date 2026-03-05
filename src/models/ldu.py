from pydantic import BaseModel, Field
from typing import List, Dict

class LDU(BaseModel):
    """Logical Document Unit: A semantically coherent chunk of content from the document."""
    
    content: str = Field(..., description="The textual content of this logical unit")
    chunk_type: str = Field(..., description="Type of chunk (e.g., 'paragraph', 'table', 'figure', 'section')")
    page_refs: List[int] = Field(..., description="List of page numbers this unit spans")
    bounding_box: Dict[str, float] = Field(..., description="Bounding box coordinates {'x0': float, 'y0': float, 'x1': float, 'y1': float}")
    parent_section: str = Field(..., description="Title or identifier of the parent section")
    token_count: int = Field(..., description="Approximate number of tokens in the content")
    content_hash: str = Field(..., description="SHA256 hash of the content for integrity checking")