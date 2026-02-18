import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.services import get_llm_completion  # Using your existing service

@dataclass
class ProcessedQuery:
    """Processed query with extracted information"""
    original: str
    expanded: str
    keywords: List[str]
    intent: str  # 'how', 'what', 'where', 'debug', 'explain', 'find', 'implement'
    filters: Dict[str, Any]
    rewritten_query: Optional[str] = None  # LLM-rewritten query for semantic search
    pseudocode_hints: Optional[str] = None  # Pseudocode for implementation queries
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original,
            "expanded": self.expanded,
            "keywords": self.keywords,
            "intent": self.intent,
            "filters": self.filters,
            "rewritten_query": self.rewritten_query,
            "pseudocode_hints": self.pseudocode_hints,
        }

class QueryProcessor:
    """Process user queries to improve retrieval with LLM-based enhancement"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Intent keywords mapping
        self.intent_patterns = {
            "how": ["how", "implement", "create", "build", "make"],
            "what": ["what", "is", "are", "does", "define", "purpose"],
            "where": ["where", "locate", "find", "which file"],
            "debug": ["error", "bug", "issue", "problem", "fix", "fail", "crash"],
            "explain": ["explain", "describe", "tell me about", "understand"],
            "find": ["find", "search", "locate", "show me", "list"],
            "implement": ["implement", "write", "code", "develop", "algorithm"],
        }
        
        # Code-related keywords to prioritize
        self.code_keywords = {
            "function", "method", "class", "module", "variable", "parameter",
            "return", "import", "export", "api", "endpoint", "route",
            "database", "query", "model", "schema", "table",
            "auth", "login", "user", "session", "test", "spec"
        }

    def process(self, query: str, conversation_history: List[Dict] = None) -> ProcessedQuery:
        """
        Main entry point to process a query.
        """
        query = query.strip()
        
        # 1. Rule-based extraction
        intent = self._detect_intent(query)
        keywords = self._extract_keywords(query)
        filters = self._extract_filters(query)
        expanded = self._expand_query(query)

        # 2. LLM Enhancement (Rewriting & Pseudocode)
        rewritten_query = None
        pseudocode_hints = None
        
        try:
            enhancements = self._enhance_with_llm(query, intent, keywords, filters, conversation_history)
            
            # Apply enhancements
            if enhancements.get("refined_intent"):
                intent = enhancements["refined_intent"]
            
            rewritten_query = enhancements.get("rewritten_query")
            pseudocode_hints = enhancements.get("pseudocode_hints")
            
            # Add LLM selected keywords to our list
            if enhancements.get("selected_keywords"):
                keywords.extend([k for k in enhancements["selected_keywords"] if k not in keywords])

        except Exception as e:
            self.logger.error(f"LLM enhancement failed: {e}")

        return ProcessedQuery(
            original=query,
            expanded=expanded,
            keywords=keywords,
            intent=intent,
            filters=filters,
            rewritten_query=rewritten_query or expanded, # Fallback to expanded if LLM fails
            pseudocode_hints=pseudocode_hints
        )

    def _detect_intent(self, query: str) -> str:
        """Rule-based intent detection."""
        query_lower = query.lower()
        scores = {intent: sum(1 for p in pats if p in query_lower) 
                  for intent, pats in self.intent_patterns.items()}
        
        best_intent = max(scores, key=scores.get)
        return best_intent if scores[best_intent] > 0 else "general"

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract significant words, removing stopwords."""
        stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "is", "of", "with"}
        words = re.findall(r'\b\w+\b', query.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def _extract_filters(self, query: str) -> Dict[str, Any]:
        """Detect file extensions or language constraints."""
        filters = {}
        # Detect file extensions like .py, .ts, etc.
        ext_match = re.search(r'\.(py|js|ts|tsx|jsx|go|rs|java|cpp|c|h)\b', query.lower())
        if ext_match:
            filters["extension"] = ext_match.group(0)
        return filters

    def _expand_query(self, query: str) -> str:
        """Simple synonym expansion."""
        synonyms = {
            "auth": "authentication authorization login",
            "db": "database sql storage",
            "repo": "repository codebase",
            "test": "unittest integration spec"
        }
        words = query.lower().split()
        expanded = [synonyms.get(w, w) for w in words]
        return " ".join(expanded)

    def _enhance_with_llm(self, query: str, intent: str, keywords: List[str], 
                          filters: Dict, history: List[Dict]) -> Dict[str, Any]:
        """Uses Lumis LLM service to generate advanced query metadata."""
        
        # Context from history if available
        context_str = ""
        if history and len(history) > 0:
            last_exchanges = history[-4:]
            context_str = "Conversation Context:\n" + "\n".join(
                [f"{msg['role'].upper()}: {msg['content']}" for msg in last_exchanges]
            )

        system_prompt = (
            "You are a code search query analyzer for a RAG system.\n"
            "Analyze the user query to improve code retrieval.\n"
            "Output fields exactly as requested."
        )

        user_prompt = f"""
            {context_str}
            User Query: "{query}"
            Current Keywords: {keywords}
            Detected Intent: {intent}

            Provide the following (in ENGLISH):
            1. REFINED_INTENT: One of [Code QA, Debugging, Implementation, Architecture, Explanation]
            2. REWRITTEN_QUERY: A keyword-rich search string optimized for embedding similarity (resolve pronouns like 'it', 'that file' using context).
            3. PSEUDOCODE_HINTS: If the user asks to implement logic, provide 3-5 lines of high-level pseudocode/logic to search for. If not, output "N/A".

            Format strictly as:
            REFINED_INTENT: <value>
            REWRITTEN_QUERY: <value>
            PSEUDOCODE_HINTS: <value>
        """
        # Call your existing service
        response = get_llm_completion(system_prompt, user_prompt, reasoning_enabled=False)
        return self._parse_llm_response(response)

    def _parse_llm_response(self, text: str) -> Dict[str, Any]:
        """Parses the text response into a dictionary."""
        result = {}
        
        # Regex to extract fields safely
        intent_match = re.search(r'REFINED_INTENT:\s*(.+)', text, re.IGNORECASE)
        query_match = re.search(r'REWRITTEN_QUERY:\s*(.+)', text, re.IGNORECASE)
        pseudo_match = re.search(r'PSEUDOCODE_HINTS:\s*(.+)', text, re.IGNORECASE | re.DOTALL)

        if intent_match:
            result['refined_intent'] = intent_match.group(1).strip()
        if query_match:
            result['rewritten_query'] = query_match.group(1).strip()
        if pseudo_match:
            hint = pseudo_match.group(1).strip()
            if "N/A" not in hint and "None" not in hint:
                result['pseudocode_hints'] = hint

        return result