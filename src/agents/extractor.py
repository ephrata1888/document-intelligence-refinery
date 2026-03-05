import json
import logging
import time
import yaml
from pathlib import Path
from typing import Dict, Any
from models.profiles import DocumentProfile
from models.extraction import NormalizedDocument, Strategy
from extractors.fast import FastTextExtractor
from extractors.layout import LayoutExtractor
from extractors.vision import VisionExtractor
from extractors import LowConfidenceError

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
        # Load profile
        profile_path = Path('.refinery/profiles') / f"{Path(pdf_path).stem}.json"
        with open(profile_path, 'r') as f:
            profile_data = json.load(f)
        profile = DocumentProfile(**profile_data)
        
        # Start with suggested strategy
        strategies = ['A', 'B', 'C']
        start_idx = strategies.index(profile.suggested_strategy)
        escalation_reason = None
        
        for i in range(start_idx, len(strategies)):
            strategy = strategies[i]
            try:
                extractor = self.extractors[strategy]
                result = extractor.extract(pdf_path)
                self._log_attempt(pdf_path, strategy, result.confidence_score, result.processing_time, result.estimated_cost, escalation_reason)
                return result
            except LowConfidenceError as e:
                escalation_reason = str(e)
                logger.info(f"Escalating {Path(pdf_path).name} from Strategy {strategy} to {strategies[i+1] if i+1 < len(strategies) else 'none'} due to {escalation_reason}")
                self._log_attempt(pdf_path, strategy, 0.0, 0.0, 0.0, escalation_reason)  # Failed attempt
                if i == len(strategies) - 1:
                    raise  # C failed, but shouldn't
                continue

    def _log_attempt(self, pdf_path: str, strategy: str, confidence: float, time_taken: float, cost: float, escalation_reason: str = None):
        entry = {
            'file_name': Path(pdf_path).name,
            'strategy': strategy,
            'confidence': confidence,
            'time': time_taken,
            'cost': cost
        }
        if escalation_reason:
            entry['escalation_reason'] = escalation_reason
        with open(self.ledger_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')