import json
import logging
import os
import time
import random
import yaml
from pathlib import Path
from typing import Dict, Any
from models.profiles import DocumentProfile
from models.extraction import NormalizedDocument, Strategy
from strategies.fast import FastTextExtractor
from strategies.layout import LayoutExtractor
from strategies.vision import VisionExtractor
from utils.exceptions import LowConfidenceError, StrategyFailure

logger = logging.getLogger(__name__)

class ExtractionRouter:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.extractors = {
            'A': FastTextExtractor(self.config),
            'B': LayoutExtractor(self.config),
            'C': VisionExtractor(self.config)
        }
        
        self.ledger_path = Path('.refinery/extraction_ledger.jsonl')
        self.ledger_path.parent.mkdir(exist_ok=True)

    def route_and_extract(self, pdf_path: str) -> NormalizedDocument:
        profile_path = Path(".refinery/profiles") / f"{Path(pdf_path).stem}.json"

        with open(profile_path, "r") as f:
            profile_data = json.load(f)

        profile = DocumentProfile(**profile_data)

        strategies = ["A", "B", "C"]
        start_idx = strategies.index(profile.suggested_strategy)
        escalation_reason = None

        for i in range(start_idx, len(strategies)):
            strategy = strategies[i]
            try:
                extractor = self.extractors[strategy]
                
                # This inner try catches the 'None' result from Strategy A
                try:
                    result = extractor.extract(pdf_path)
                    if result is None:
                        raise StrategyFailure("Strategy A returned nothing")
                except Exception as e:
                    raise StrategyFailure(f"Execution failed: {e}")


                if not hasattr(result, "pages"):
                    raise StrategyFailure("Invalid result object")

                self._add_provenance(result, pdf_path)

                # SUCCESS PATH: Pass None for escalation_reason here
                self._log_attempt(
                    pdf_path,
                    strategy,
                    result.confidence_score,
                    result.processing_time,
                    result.estimated_cost,
                    None, 
                )

                return result

            except (LowConfidenceError, StrategyFailure) as e:
                escalation_reason = str(e)
                logger.info(f"Escalating {Path(pdf_path).name} from Strategy {strategy}: {escalation_reason}")

                self._log_attempt(
                    pdf_path,
                    strategy,
                    0.0,
                    0.0,
                    0.0,
                    escalation_reason,
                )

                if i == len(strategies) - 1:
                    raise
                continue
    def _add_provenance(self, doc: NormalizedDocument, pdf_path: str):
        # Add ProvenanceChain for each text block and table
        import hashlib
        from models.provenance import ProvenanceChain
        for page_idx, page in enumerate(doc.pages):
            provenance_list = []
            # For text
            if page.text and page.text_bbox:
                bbox = page.text_bbox
                text_hash = hashlib.sha256(f"{page.text}_{bbox.x0},{bbox.y0},{bbox.x1},{bbox.y1}_{page_idx}".encode('utf-8')).hexdigest()
                provenance_list.append(ProvenanceChain(
                    document_name=doc.doc_id,
                    page_no=page_idx,
                    bbox=[bbox.x0, bbox.y0, bbox.x1, bbox.y1],
                    content_hash=text_hash
                ))
            # For tables
            for tbl in page.tables:
                if tbl.bbox:
                    bbox = tbl.bbox
                    table_content = f"table_{tbl.headers}_{tbl.rows}"
                    table_hash = hashlib.sha256(f"{table_content}_{bbox.x0},{bbox.y0},{bbox.x1},{bbox.y1}_{page_idx}".encode('utf-8')).hexdigest()
                    provenance_list.append(ProvenanceChain(
                        document_name=doc.doc_id,
                        page_no=page_idx,
                        bbox=[bbox.x0, bbox.y0, bbox.x1, bbox.y1],
                        content_hash=table_hash
                    ))
            page.provenance = provenance_list

    def _log_attempt(self, pdf_path: str, strategy: str, confidence: float, time_taken: float, cost: float, reason: str = None):
        entry = {
            "file_name": Path(pdf_path).name,
            "strategy": strategy,
            "confidence": confidence,
            "time": time_taken,
            "cost": cost,
            "escalation_reason": reason
        }
        with open(self.ledger_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')