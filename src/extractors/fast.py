import pdfplumber
import time
from typing import List, Dict
from models.extraction import NormalizedDocument, PageContent, Strategy
from . import BaseExtractor, LowConfidenceError

class FastTextExtractor(BaseExtractor):
    def __init__(self, config: dict):
        self.config = config

    def extract(self, pdf_path: str) -> NormalizedDocument:
        start_time = time.time()
        
        with pdfplumber.open(pdf_path) as pdf:
            pages_content = []
            confidence_signals = []
            
            for page in pdf.pages:
                # Extract text
                text = page.extract_text() or ""
                
                # Signal 1: Character Density
                char_count = len(text)
                page_area = page.width * page.height if page.width and page.height else 1
                density = char_count / page_area
                confidence_signals.append(min(density / 0.01, 1.0))  # Normalize, assuming 0.01 is high density
                
                # Signal 2: Image-to-Page Area Ratio
                images = page.images
                image_area = sum(img['width'] * img['height'] for img in images) if images else 0
                image_ratio = image_area / page_area if page_area > 0 else 0
                image_conf = 1.0 - min(image_ratio, 1.0)  # Lower ratio = higher confidence
                confidence_signals.append(image_conf)
                
                # Signal 3: Font Metadata Presence
                font_conf = 1.0 if page.objects.get('fontname') else 0.0
                confidence_signals.append(font_conf)
                
                # For tables, pdfplumber can extract tables
                tables = page.extract_tables() or []
                tables_dict = [{"data": table} for table in tables] if tables else []
                
                page_conf = sum(confidence_signals[-3:]) / 3  # Average of last 3 signals
                
                pages_content.append(PageContent(
                    text=text,
                    tables=tables_dict,
                    page_confidence=page_conf
                ))
        
        # Overall confidence: average of all page confidences
        if pages_content:
            confidence_score = sum(p.page_confidence for p in pages_content) / len(pages_content)
        else:
            confidence_score = 0.0
        
        processing_time = time.time() - start_time
        estimated_cost = 0.0  # No API cost for pdfplumber
        
        doc = NormalizedDocument(
            doc_id=pdf_path.split('/')[-1].split('\\')[-1],  # filename
            strategy_used=Strategy.A,
            confidence_score=confidence_score,
            processing_time=processing_time,
            estimated_cost=estimated_cost,
            pages=pages_content
        )
        
        if confidence_score < self.config.get('min_confidence_threshold', 0.85):
            raise LowConfidenceError(f"Confidence {confidence_score:.2f} below threshold")
        
        return doc