from __future__ import annotations

import logging
import os
import re
from typing import List, Dict, Optional

import google.generativeai as genai

from models.page_index import PageIndex
from models.ldu import LDU

LOG = logging.getLogger(__name__)

class PageIndexBuilder:
    def __init__(self, config: dict):
        self.config = config
        api_key = os.getenv('GOOGLE_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5')
        else:
            LOG.warning('GOOGLE_API_KEY not set; summaries will be empty')
            self.model = None

    def build(self, doc_id: str, ldus: List[LDU]) -> PageIndex:
        # group LDUs by section
        sections: Dict[str, List[LDU]] = {}
        for ldu in ldus:
            sections.setdefault(ldu.parent_section or 'root', []).append(ldu)
        # create root node
        root = PageIndex(
            title='root',
            page_range=(0, 0),
            child_sections=[],
            entities=[],
            summary='',
        )
        # recursively build nodes
        for section, units in sections.items():
            page_nums = sorted({p for u in units for p in u.page_refs})
            data_types = list({u.chunk_type for u in units})
            node = PageIndex(
                title=section,
                page_range=(page_nums[0], page_nums[-1]) if page_nums else (0,0),
                child_sections=[],
                entities=[],
                summary=self._summarize_section(units),
                data_types_present=data_types,
            )
            # key_entities: naive extract of capitalized words
            ents = set()
            for u in units:
                ents.update(re.findall(r"\b[A-Z][a-z]+\b", u.content))
            node.entities = list(ents)
            root.child_sections.append(node)
        return root

    def _summarize_section(self, units: List[LDU]) -> str:
        text = '\n'.join(u.content for u in units)
        if not self.model:
            return ""  # no summary available
        prompt = f"Summarize the following text in 2-3 sentences:\n{text}"
        resp = self.model.generate_content([prompt])
        return resp.text.strip()

    def pageindex_query(self, root: PageIndex, topic: str) -> List[PageIndex]:
        # simple relevance by substring match in title/summary
        scored: List[tuple[float, PageIndex]] = []
        def recurse(node: PageIndex):
            score = 0.0
            if topic.lower() in node.title.lower():
                score += 1.0
            if topic.lower() in node.summary.lower():
                score += 0.5
            scored.append((score, node))
            for child in node.child_sections:
                recurse(child)
        recurse(root)
        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for score,node in scored[:3] if score>0]
