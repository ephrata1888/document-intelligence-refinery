from abc import ABC, abstractmethod
from typing import Union
from models.extraction import NormalizedDocument

class LowConfidenceError(Exception):
    pass

class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, pdf_path: str) -> NormalizedDocument:
        pass