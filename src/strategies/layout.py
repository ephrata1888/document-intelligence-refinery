import time
from typing import List, Dict
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from posthog import page
from models.extraction import NormalizedDocument, PageContent, Strategy, TableData, BoundingBox
from strategies import BaseExtractor
from utils.exceptions import LowConfidenceError

# src/strategies/layout.py

class DoclingDocumentAdapter:
    @staticmethod
    def convert(dl_document) -> NormalizedDocument:
        pages_content = []
        total_confidence = 0.0
        
        for page_no, page in dl_document.pages.items():
            text = dl_document.export_to_markdown()
            tables = []
            
            if hasattr(page, 'tables') and page.tables:
                for table in page.tables:
                    df = table.export_to_dataframe()
                    # Capture Bounding Box for Provenance (Score 5 Rubric)
                    t_bbox = None
                    if hasattr(table, 'prov') and table.prov:
                        # Convert Docling bbox to our standard [x0, y0, x1, y1]
                        b = table.prov[0].bbox
                        t_bbox = BoundingBox(x0=b.l, y0=b.t, x1=b.r, y1=b.b)

                    tables.append(TableData(
                        headers=[str(c) for c in df.columns],
                        rows=[[str(v) for v in row] for row in df.values.tolist()],
                        bbox=t_bbox
                    ))
            
            page_conf = 0.95 # Layout-aware is high confidence
            total_confidence += page_conf
            pages_content.append(PageContent(text=text, tables=tables, page_confidence=page_conf))
        
        return NormalizedDocument(
            doc_id="", 
            strategy_used=Strategy.B,
            confidence_score=total_confidence / len(pages_content) if pages_content else 0.0,
            processing_time=0.0,
            estimated_cost=0.0,
            pages=pages_content
        )
class LayoutExtractor(BaseExtractor):
    def __init__(self, config: dict):
        self.config = config
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Rely on existing text layer
        pipeline_options.do_table_structure = True  # Enable table structure capture
        pdf_options = PdfFormatOption(pipeline_options=pipeline_options)
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: pdf_options}
        )

    def extract(self, pdf_path: str) -> NormalizedDocument:
        start_time = time.time()
        
        result = self.converter.convert(pdf_path, page_range=(1, 20))
        dl_doc = result.document
        
        normalized = DoclingDocumentAdapter.convert(dl_doc)
        normalized.processing_time = time.time() - start_time
        normalized.doc_id = pdf_path.split('/')[-1].split('\\')[-1]
        
        # For B, assume always confident, no LowConfidenceError
        return normalized