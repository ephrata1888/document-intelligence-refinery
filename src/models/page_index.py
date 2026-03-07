from pydantic import BaseModel, Field
from typing import List, Optional, ForwardRef

PageIndexRef = ForwardRef('PageIndex')

class PageIndex(BaseModel):
    """Recursive tree structure representing the document's table of contents and sections."""
    
    title: str = Field(..., description="Title of this section")
    page_range: tuple[int, int] = Field(..., description="Start and end page numbers (inclusive)")
    child_sections: List[PageIndexRef] = Field(default_factory=list, description="Nested subsections")
    entities: List[str] = Field(default_factory=list, description="Named entities mentioned in this section")
    data_types_present: List[str] = Field(default_factory=list, description="Types of data/chunks found in this section")
    summary: str = Field(..., description="Brief summary of the section content")

PageIndex.model_rebuild()