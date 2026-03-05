import time
from typing import List, Dict
from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from models.extraction import NormalizedDocument, PageContent, Strategy
from . import BaseExtractor, LowConfidenceError

class DoclingDocumentAdapter:
    @staticmethod
    def convert(dl_document) -> NormalizedDocument:
        pages_content = []
        total_confidence = 0.0
        
        for page in dl_document.pages:
            text = page.get_text()
            tables = []
            if hasattr(page, 'tables') and page.tables:
                for table in page.tables:
                    # Assuming table has export_to_dataframe or similar
                    if hasattr(table, 'export_to_dataframe'):
                        df = table.export_to_dataframe()
                        tables.append({"data": df.to_dict('records')})
                    else:
                        tables.append({"data": []})  # Placeholder
            
            # Assume confidence based on text length or something
            page_conf = min(len(text) / 1000, 1.0) if text else 0.5
            total_confidence += page_conf
            
            pages_content.append(PageContent(
                text=text,
                tables=tables,
                page_confidence=page_conf
            ))
        
        confidence_score = total_confidence / len(pages_content) if pages_content else 0.0
        
        return NormalizedDocument(
            doc_id="",  # Will be set in extract
            strategy_used=Strategy.B,
            confidence_score=confidence_score,
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
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: pipeline_options}
        )

    def extract(self, pdf_path: str) -> NormalizedDocument:
        start_time = time.time()
        
        result = self.converter.convert(pdf_path)
        dl_doc = result.document
        
        normalized = DoclingDocumentAdapter.convert(dl_doc)
        normalized.processing_time = time.time() - start_time
        normalized.doc_id = pdf_path.split('/')[-1].split('\\')[-1]
        
        # For B, assume always confident, no LowConfidenceError
        return normalized