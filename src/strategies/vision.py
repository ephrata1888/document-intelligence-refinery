import time
import os
import json
import tempfile
import ollama
from typing import List, Dict
from pdf2image import convert_from_path
from models.extraction import NormalizedDocument, PageContent, Strategy, TableData, BoundingBox
from utils.exceptions import LowConfidenceError, StrategyFailure
from strategies import BaseExtractor

class VisionExtractor(BaseExtractor):
    def __init__(self, config: dict):
        self.config = config
        
    def extract(self, pdf_path: str) -> NormalizedDocument:
        start_time = time.time()
        
        # Convert PDF to images
        images = convert_from_path(pdf_path)
        
        pages_content = []
        total_confidence = 0.0
        
        for page_num, image in enumerate(images):
            # Save image to temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
                image.save(temp_path, 'PNG')
            
            try:
                # Call Ollama with llama3.2-vision
                prompt = "Act as an expert OCR and table extraction agent. Extract all text and maintain the structure of every table found on this page. Return only valid JSON in the format: {'text': 'full text of page', 'tables': [{'headers': ['col1', 'col2'], 'rows': [['val1', 'val2']], 'caption': 'optional'}]}"
                response = ollama.chat(
                    model='llama3.2-vision',
                    messages=[{
                        'role': 'user',
                        'content': prompt,
                        'images': [temp_path]
                    }]
                )
                
                # Parse response
                content = response['message']['content']
                # Handle markdown backticks
                if content.startswith('```json'):
                    content = content[7:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                try:
                    page_data = json.loads(content)
                except json.JSONDecodeError:
                    # Fallback if not JSON
                    page_data = {'text': content, 'tables': []}
                
                text = page_data.get('text', '')
                tables_data = page_data.get('tables', [])
                tables = []
                for tbl_data in tables_data:
                    headers = tbl_data.get('headers', [])
                    rows = tbl_data.get('rows', [])
                    caption = tbl_data.get('caption')
                    tables.append(TableData(
                        headers=headers,
                        rows=rows,
                        caption=caption,
                        bbox=None  # VLM doesn't provide bboxes
                    ))
                
                # Check if all requested fields are present
                has_text = bool(text and text.strip() and text.lower() not in ['n/a', 'none'])
                has_tables = len(tables) > 0
                if has_text and has_tables:
                    page_conf = 0.98
                elif has_text:
                    page_conf = 0.85  # Text present but no tables
                else:
                    page_conf = 0.5  # Missing text
                total_confidence += page_conf
                
                pages_content.append(PageContent(
                    text=text,
                    tables=tables,
                    page_confidence=page_conf
                ))
            
            except Exception as e:
                raise StrategyFailure(f"Ollama extraction failed for page {page_num + 1}: {str(e)}")
            finally:
                # Clean up temp file
                os.unlink(temp_path)
        
        confidence_score = total_confidence / len(pages_content) if pages_content else 0.0
        processing_time = time.time() - start_time
        
        doc_data = {
            "doc_id": os.path.basename(pdf_path),
            "strategy_used": Strategy.C,
            "confidence_score": confidence_score,
            "processing_time": processing_time,
            "estimated_cost": 0.0,  # No cost for local Ollama
            "pages": pages_content,
        }

        doc = NormalizedDocument(**doc_data)