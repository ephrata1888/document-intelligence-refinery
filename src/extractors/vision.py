import time
import os
import json
from typing import List, Dict
import google.generativeai as genai
from models.extraction import NormalizedDocument, PageContent, Strategy
from . import BaseExtractor, LowConfidenceError

class BudgetExceeded(Exception):
    pass

class BudgetGuard:
    def __init__(self, config: dict):
        self.max_budget = config.get('max_doc_budget_usd', 0.05)
        self.cost_per_1k = config.get('cost_per_1k_tokens_vlm', 0.0001)

    def check_budget(self, estimated_tokens: int) -> float:
        estimated_cost = (estimated_tokens / 1000) * self.cost_per_1k
        if estimated_cost > self.max_budget:
            raise BudgetExceeded(f"Estimated cost {estimated_cost:.4f} exceeds budget {self.max_budget}")
        return estimated_cost

    def calculate_actual_cost(self, usage_metadata) -> float:
        total_tokens = usage_metadata.total_token_count if hasattr(usage_metadata, 'total_token_count') else 0
        return (total_tokens / 1000) * self.cost_per_1k

class VisionExtractor(BaseExtractor):
    def __init__(self, config: dict):
        self.config = config
        self.budget_guard = BudgetGuard(config)
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def extract(self, pdf_path: str) -> NormalizedDocument:
        start_time = time.time()
        
        # Upload the PDF file
        uploaded_file = genai.upload_file(pdf_path)
        
        # Wait for processing
        while uploaded_file.state.name != 'ACTIVE':
            time.sleep(1)
            uploaded_file = genai.get_file(uploaded_file.name)
        
        # Estimate tokens roughly for budget check (assume 1000 tokens per page)
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
        estimated_tokens = page_count * 1000
        self.budget_guard.check_budget(estimated_tokens)
        
        # Generate content
        prompt = "Act as an expert OCR and table extraction agent. Extract all text and maintain the structure of every table found on these pages. Return only valid JSON in the format: {'pages': [{'text': 'full text of page', 'tables': [{'data': table_rows}]}]}"
        response = self.model.generate_content([prompt, uploaded_file])
        
        # Parse response
        try:
            result = json.loads(response.text)
            pages_data = result.get('pages', [])
        except json.JSONDecodeError:
            # Fallback if not JSON
            pages_data = [{'text': response.text, 'tables': []}]
        
        pages_content = []
        total_confidence = 0.0
        
        for page_data in pages_data:
            text = page_data.get('text', '')
            tables = page_data.get('tables', [])
            page_conf = 0.95  # Assume high for vision
            total_confidence += page_conf
            
            pages_content.append(PageContent(
                text=text,
                tables=tables,
                page_confidence=page_conf
            ))
        
        confidence_score = total_confidence / len(pages_content) if pages_content else 0.0
        processing_time = time.time() - start_time
        actual_cost = self.budget_guard.calculate_actual_cost(response.usage_metadata) if hasattr(response, 'usage_metadata') else 0.0
        
        doc = NormalizedDocument(
            doc_id=os.path.basename(pdf_path),
            strategy_used=Strategy.C,
            confidence_score=confidence_score,
            processing_time=processing_time,
            estimated_cost=actual_cost,  # Use actual
            pages=pages_content
        )
        
        return doc