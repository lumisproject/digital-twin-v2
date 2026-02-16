import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from src.services import get_llm_completion

class AnswerGenerator:
    """
    Generates evidence-based answers. Strictly forbids guessing architecture from file names.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.logger = logging.getLogger(__name__)

    def generate(self, query: str, collected_elements: List[Dict[str, Any]], repo_structure: str = None, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        
        # 1. Format the Context
        context_str = self._prepare_context(collected_elements)
        
        # 2. Stricter System Prompt
        system_prompt = (
            "You are Lumis, an expert Senior Software Architect.\n"
            "Your goal is to answer user questions about a codebase using ONLY the provided code snippets.\n\n"
            "STRICT RULES:\n"
            "1. NO GUESSING: Do NOT infer architecture from file names. If the 'RETRIEVED CODE' section is empty or irrelevant, you MUST say: 'I could not find the specific implementation for this in the codebase.'\n"
            "2. CITATIONS: Cite sources using brackets, e.g., [src/auth.py].\n"
            "3. TECHNICAL DEPTH: Explain the logic flow, variables, and dependencies found in the snippets.\n"
            "4. INTERNAL SUMMARY: End with a hidden <SUMMARY> block analyzing the findings."
        )

        # 3. Build the User Prompt
        history_text = ""
        if history:
            recent = history[-6:]
            history_text = "PREVIOUS CONVERSATION:\n" + "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent]) + "\n\n"

        user_prompt = (
            f"{history_text}"
            f"USER QUERY: {query}\n\n"
            f"RETRIEVED CODE:\n{context_str}\n\n"
            "INSTRUCTIONS:\n"
            "- If code is present, explain how it works in detail.\n"
            "- If code is missing, do NOT use file names to guess implementation.\n"
            "- Reference specific file names and line contents.\n"
            "- End with <SUMMARY>Files Analyzed; Evidence Found</SUMMARY>"
        )
        
        # 4. Execute (Using default reasoning=False for speed in generation)
        raw_response = get_llm_completion(system_prompt, user_prompt)
        
        # 5. Parse
        answer, summary = self._parse_summary(raw_response)
        
        return {
            "answer": answer,
            "summary": summary,
            "sources": [e.get('file_path', 'unknown') for e in collected_elements]
        }

    def _prepare_context(self, elements: List[Dict[str, Any]]) -> str:
        if not elements:
            return "NO CODE SNIPPETS RETRIEVED."
        
        seen = set()
        parts = []
        for elem in elements:
            # Deduplicate by content to save tokens
            content_hash = hash(elem.get('content', ''))
            if content_hash not in seen:
                seen.add(content_hash)
                parts.append(f"### File: {elem.get('file_path')} (Unit: {elem.get('unit_name')})\n```python\n{elem.get('content')}\n```")
        
        return "\n\n".join(parts)

    def _parse_summary(self, text: str) -> Tuple[str, Optional[str]]:
        if not text: return "Error: No response.", None
        match = re.search(r'<SUMMARY>(.*?)</SUMMARY>', text, re.DOTALL | re.IGNORECASE)
        if match:
            summary = match.group(1).strip()
            answer = re.sub(r'<SUMMARY>.*?</SUMMARY>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            return answer, summary
        return text, None