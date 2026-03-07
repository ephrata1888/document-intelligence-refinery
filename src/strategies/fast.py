import pdfplumber
import time
from typing import List, Dict
from models.extraction import NormalizedDocument, PageContent, Strategy, TableData, BoundingBox
from strategies import BaseExtractor
from utils.exceptions import LowConfidenceError

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
                high_density = self.config.get('high_density_threshold', 0.01)
                confidence_signals.append(min(density / high_density, 1.0))  # Normalize
                
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
                tables = []
                for tbl in page.find_tables():
                    extracted_table = tbl.extract()
                    if extracted_table:
                        headers = extracted_table[0] if extracted_table else []
                        rows = extracted_table[1:] if len(extracted_table) > 1 else []
                        bbox = BoundingBox(
                            x0=tbl.bbox[0],
                            y0=tbl.bbox[1],
                            x1=tbl.bbox[2],
                            y1=tbl.bbox[3],
                            page_index = getattr(page, 'page_no', 1) - 1
                        )
                        tables.append(TableData(
                            headers=headers,
                            rows=rows,
                            caption=None,  # pdfplumber doesn't extract captions
                            bbox=bbox
                        ))
                
                # Get text bbox
                text_bbox = None
                if text:
                    chars = page.chars
                    if chars:
                        x0 = min(c['x0'] for c in chars)
                        y0 = min(c['top'] for c in chars)  # top is y0
                        x1 = max(c['x1'] for c in chars)
                        y1 = max(c['bottom'] for c in chars)  # bottom is y1
                        text_bbox = BoundingBox(
                            x0=x0,
                            y0=y0,
                            x1=x1,
                            y1=y1,
                            page_index = getattr(page, 'page_no', 1) - 1 
                       )
                
                page_conf = sum(confidence_signals[-3:]) / 3  # Average of last 3 signals
                
                pages_content.append(PageContent(
                    text=text,
                    tables=tables,
                    page_confidence=page_conf,
                    text_bbox=text_bbox  # Add this if we add to model
                ))
        
        # Overall confidence: average of all page confidences
        if pages_content:
            confidence_score = sum(p.page_confidence for p in pages_content) / len(pages_content)
        else:
            confidence_score = 0.0
        
        processing_time = time.time() - start_time
        estimated_cost = 0.0  # No API cost for pdfplumber
        
        
        doc_data = {
            "doc_id": pdf_path.split("/")[-1].split("\\")[-1],
            "strategy_used": Strategy.A,
            "confidence_score": confidence_score,
            "processing_time": processing_time,
            "estimated_cost": estimated_cost,
            "pages": pages_content,
        }

        doc = NormalizedDocument(**doc_data)
        
        if confidence_score < self.config.get('min_confidence_threshold', 0.85):
            raise LowConfidenceError(f"Confidence {confidence_score:.2f} below threshold")
        
        return doc