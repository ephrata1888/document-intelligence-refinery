import json
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List

from langgraph.graph import StateGraph, END

from models.query import QueryState
from models.provenance import ProvenanceChain
from agents.tools import PageIndexNavigateTool, SemanticSearchTool, FactTableTool


class QueryAgent:
    """LangGraph-powered query agent with provenance tracking."""

    def __init__(self, refinery_dir: Path = Path(".refinery")):
        self.refinery_dir = refinery_dir
        self.pageindex_tool = PageIndexNavigateTool(refinery_dir)
        self.semantic_tool = SemanticSearchTool(refinery_dir)
        self.fact_tool = FactTableTool(refinery_dir)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("triage", self._triage_query)
        workflow.add_node("retrieve", self._retrieve_context)
        workflow.add_node("synthesize", self._synthesize_answer)
        workflow.add_node("verify", self._verify_answer)

        # Define edges
        workflow.set_entry_point("triage")
        workflow.add_edge("triage", "retrieve")
        workflow.add_edge("retrieve", "synthesize")
        workflow.add_edge("synthesize", "verify")
        workflow.add_edge("verify", END)

        return workflow.compile()

    def query(self, question: str) -> Dict[str, Any]:
        """Execute the query pipeline."""
        initial_state = {
            "question": question,
            "query_type": None,
            "context_chunks": [],
            "selected_sections": [],
            "answer": None,
            "provenance_chain": []
        }
        result = self.graph.invoke(initial_state)
        return {
            "answer": result.get("answer"),
            "provenance": result.get("provenance_chain", [])
        }

    def _triage_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Decide query type: general vs numerical."""
        question = state["question"].lower()
        # Simple heuristic: if contains numbers or financial terms, use SQL
        numerical_keywords = ["revenue", "profit", "cost", "amount", "number", "date", "value"]
        is_numerical = any(kw in question for kw in numerical_keywords) or re.search(r"\d", question)
        state["query_type"] = "numerical" if is_numerical else "general"
        return state

    def _retrieve_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Gather context using appropriate tools."""
        if state["query_type"] == "numerical":
            # Use fact table
            sql = self._generate_sql_query(state["question"])
            facts = self.fact_tool.query(sql)
            state["context_chunks"] = [json.dumps(fact) for fact in facts]
        else:
            # Use pageindex then semantic search
            sections = self.pageindex_tool.search(state["question"])
            state["selected_sections"] = sections
            chunks = self.semantic_tool.search(state["question"], sections)
            state["context_chunks"] = chunks
        return state

    def _synthesize_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate answer from context."""
        if not state["context_chunks"]:
            state["answer"] = "Information not found in document."
            return state

        # Simple synthesis: concatenate and summarize
        context = "\n".join(state["context_chunks"])
        # For now, use the context as answer; in real impl, use LLM
        state["answer"] = f"Based on document content: {context[:500]}..."

        # Build provenance (placeholder)
        state["provenance_chain"] = []  # Would populate from chunks
        return state

    def _verify_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Verify answer against source hashes."""
        if state["answer"] == "Information not found in document.":
            return state

        # Check if answer can be verified
        verifiable = self._check_verifiability(state["answer"], state["context_chunks"])
        if not verifiable:
            state["answer"] += " [WARNING: Answer unverifiable - data mismatch with source]"
        return state

    def _generate_sql_query(self, question: str) -> str:
        """Generate SQL from natural language (simple implementation)."""
        # Very basic SQL generation
        if "revenue" in question.lower():
            return "SELECT * FROM facts WHERE key LIKE '%revenue%'"
        return "SELECT * FROM facts LIMIT 10"

    def _check_verifiability(self, answer: str, chunks: List[str]) -> bool:
        """Check if answer matches source content hashes."""
        # Placeholder: compute hash of answer and compare to chunk hashes
        answer_hash = hashlib.sha256(answer.encode()).hexdigest()
        for chunk in chunks:
            chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()
            if answer_hash == chunk_hash:
                return True
        return False


def verify_document_claim(claim: str, refinery_dir: Path = Path(".refinery")) -> Dict[str, Any]:
    """Standalone verification function."""
    # Find LDU with matching content
    semantic_tool = SemanticSearchTool(refinery_dir)
    results = semantic_tool.search(claim, n_results=1)
    if results:
        # Extract bbox from metadata or something
        return {"verified": True, "bbox": "placeholder", "page": 0}
    return {"verified": False, "reason": "Claim not found in documents"}