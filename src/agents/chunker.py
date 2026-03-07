from __future__ import annotations

import hashlib
import logging
import re
from typing import List, Optional

from pathlib import Path
import yaml

from models.extraction import NormalizedDocument, TableData, BoundingBox
from models.ldu import LDU

LOG = logging.getLogger(__name__)



class ChunkValidator:
    def __init__(self, config: dict):
        # configuration thresholds
        self.max_list_tokens = config.get("max_list_tokens", 200)

    def validate(self, ldus: List[LDU]) -> List[LDU]:
        # enforce list cohesion: split lists that exceed token threshold
        validated: List[LDU] = []
        for ldu in ldus:
            if ldu.chunk_type == "list" and ldu.token_count > self.max_list_tokens:
                # naive split by lines
                lines = ldu.content.splitlines()
                chunk = []
                tokens = 0
                for line in lines:
                    tok = len(line.split())
                    if tokens + tok > self.max_list_tokens and chunk:
                        # emit previous chunk
                        text = "\n".join(chunk)
                        bbox = ldu.bounding_box
                        new_hash = hashlib.sha256((text + str(bbox)).encode('utf-8')).hexdigest()
                        validated.append(
                            LDU(
                                content=text,
                                chunk_type="list",
                                page_refs=ldu.page_refs,
                                bounding_box=ldu.bounding_box,
                                parent_section=ldu.parent_section,
                                token_count=tokens,
                                content_hash=new_hash,
                            )
                        )
                        chunk = []
                        tokens = 0
                    chunk.append(line)
                    tokens += tok
                if chunk:
                    text = "\n".join(chunk)
                    bbox = ldu.bounding_box
                    new_hash = hashlib.sha256((text + str(bbox)).encode('utf-8')).hexdigest()
                    validated.append(
                        LDU(
                            content=text,
                            chunk_type="list",
                            page_refs=ldu.page_refs,
                            bounding_box=ldu.bounding_box,
                            parent_section=ldu.parent_section,
                            token_count=tokens,
                            content_hash=new_hash,
                        )
                    )
            else:
                validated.append(ldu)
        return validated

class ChunkingEngine:
    def __init__(self, config_path: Path | str = "rubric/extraction_rules.yaml"):
        # Use helper to turn the path into a dictionary
        self.config = self._load_config(config_path)
        self.validator = ChunkValidator(self.config)
        self.header_re = re.compile(rf"^(?:[A-Z][A-Za-z0-9 ]{{1,{self.config.get('header_regex_max_length', 50)}}})$")
        self.crossref_re = re.compile(r"see (?:Table|Section) \w+", re.IGNORECASE)

    def _load_config(self, path: Path | str) -> dict:
        p = Path(path)

        if not p.exists():
            print(f"Config file {p} not found")
            return {}

        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def _make_hash(self, text: str, bbox: Optional[BoundingBox]) -> str:
        if bbox:
            bbox_str = f"{bbox.x0},{bbox.y0},{bbox.x1},{bbox.y1}"
            input_str = f"{text}_{bbox_str}_{bbox.page_index}"
        else:
            input_str = f"{text}_no_bbox_-1"
        return hashlib.sha256(input_str.encode("utf-8")).hexdigest()

    def chunk(self, doc: NormalizedDocument) -> List[LDU]:
        ldus: List[LDU] = []
        current_section: Optional[str] = None

        for page_idx, page in enumerate(doc.pages):
            text = page.text or ""
            # detect header
            if text and self.header_re.match(text.strip()):
                current_section = text.strip()
            # split paragraphs by blank lines
            # split into paragraphs but preserve numbered/bullet lists
            raw_blocks = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
            for para in raw_blocks:
                # list detection
                lines = para.strip().splitlines()
                is_list = all(re.match(r"^(?:\d+\.|\u2022|\*|\-)", ln.strip()) for ln in lines if ln.strip())
                if is_list:
                    bbox = BoundingBox(0, 0, 0, 0, page_idx)
                    ldu = LDU(
                        content=para,
                        chunk_type="list",
                        page_refs=[page_idx],
                        bounding_box={
                            "x0": bbox.x0,
                            "y0": bbox.y0,
                            "x1": bbox.x1,
                            "y1": bbox.y1,
                            "page_index": bbox.page_index,
                        },
                        parent_section=current_section or "",
                        token_count=len(para.split()),
                        content_hash=self._make_hash(para, bbox),
                    )
                    ldus.append(ldu)
                    continue
                # normal paragraph
                cross_refs = self.crossref_re.findall(para)
                bbox = BoundingBox(0, 0, 0, 0, page_idx)  # placeholder; could use word coords
                ldu = LDU(
                    content=para,
                    chunk_type="paragraph",
                    page_refs=[page_idx],
                    bounding_box={
                        "x0": bbox.x0,
                        "y0": bbox.y0,
                        "x1": bbox.x1,
                        "y1": bbox.y1,
                        "page_index": bbox.page_index,
                    },
                    parent_section=current_section or "",
                    token_count=len(para.split()),
                    content_hash=self._make_hash(para, bbox),
                )
                if cross_refs:
                    ldu.metadata = {"cross_refs": cross_refs}
                if current_section:
                    ldu.metadata = ldu.metadata or {}
                    ldu.metadata["section"] = current_section
                # caption anchor
                if para.strip().lower().startswith(('table', 'figure')) and ldus:
                    prev = ldus[-1]
                    prev.metadata = prev.metadata or {}
                    prev.metadata['caption'] = para.strip()
                    continue
                ldus.append(ldu)
            # tables
            for tbl in page.tables:
                # table integrity: one LDU per table
                bbox = tbl.bbox if hasattr(tbl, "bbox") else None
                table_content = f"table_{tbl.headers}_{tbl.rows}"
                ldu = LDU(
                    content=table_content,
                    chunk_type="table",
                    page_refs=[page_idx],
                    bounding_box={
                        "x0": bbox.x0 if bbox else 0,
                        "y0": bbox.y0 if bbox else 0,
                        "x1": bbox.x1 if bbox else 0,
                        "y1": bbox.y1 if bbox else 0,
                        "page_index": page_idx,
                    },
                    parent_section=current_section or "",
                    token_count=0,
                    content_hash=self._make_hash(table_content, bbox),
                )
                ldus.append(ldu)
        # post-validate
        return self.validator.validate(ldus)
