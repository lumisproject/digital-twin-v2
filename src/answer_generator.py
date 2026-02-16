import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from src.services import get_llm_completion

class AnswerGenerator:
    """
    Generates high-quality, cited answers using the FastCode prompting strategy.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.logger = logging.getLogger(__name__)

    def generate(self, query: str, collected_elements: List[Dict[str, Any]], repo_structure: str = None, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        
        # 1. Format the Context
        context_str = self._prepare_context(collected_elements)
        
        # 2. Build the System Prompt
        system_prompt = (
            "You are Lumis, an expert Senior Software Architect and Code Analyst.\n"
            "Your goal is to answer user questions about a codebase accurately, using ONLY the provided context.\n\n"
            "STRICT RULES:\n"
            "1. CITATIONS: You MUST cite your sources. When referring to code, append the file path in brackets, e.g., 'The auth logic is in `src/auth.py` [src/auth.py]'.\n"
            "2. NO HALLUCINATION: If the provided context is empty or insufficient, explicitly state: 'I could not find the answer in the retrieved files.' Do not guess.\n"
            "3. MISSING README: If the context contains a 'Repository Structure' but no code snippets, infer the project purpose from the file names.\n"
            "4. INTERNAL SUMMARY: You MUST end your response with a hidden <SUMMARY> block analyzing what you found."
        )

        # 3. Build the User Prompt
        history_text = ""
        if history:
            recent = history[-6:] # Keep last few turns
            history_text = "PREVIOUS CONVERSATION:\n" + "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent]) + "\n\n"

        structure_section = ""
        if repo_structure:
            structure_section = f"REPOSITORY STRUCTURE (File Names):\n{repo_structure}\n\n"

        user_prompt = (
            f"{history_text}"
            f"USER QUERY: {query}\n\n"
            f"{structure_section}"
            f"RETRIEVED CODE SNIPPETS:\n{context_str}\n\n"
            "INSTRUCTIONS:\n"
            "- Answer the user's query in technical detail.\n"
            "- Use the File Names to explain architecture if code is missing.\n"
            "- Reference specific file names.\n"
            "- End with <SUMMARY>Files Analyzed; Key Findings</SUMMARY>"
        )
        
        # 4. Execute
        raw_response = get_llm_completion(system_prompt, user_prompt)
        
        # 5. Parse
        answer, summary = self._parse_summary(raw_response)
        
        return {
            "answer": answer,
            "summary": summary,
            "sources": [e.get('file_path', 'unknown') for e in collected_elements]
        }

    def _prepare_context(self, elements: List[Dict[str, Any]]) -> str:
        """Formats the retrieved code chunks into a readable structure."""
        if not elements:
            return "No specific code snippets retrieved."
        
        # Deduplicate based on ID
        seen = set()
        unique = []
        for e in elements:
            if e['id'] not in seen:
                seen.add(e['id'])
                unique.append(e)

        parts = []
        for i, elem in enumerate(unique):
            parts.append(f"### Source {i+1}: {elem.get('file_path')} ({elem.get('unit_name')})\n```python\n{elem.get('content')}\n```")
        
        return "\n\n".join(parts)

    def _parse_summary(self, text: str) -> Tuple[str, Optional[str]]:
        if not text: return "Error: No response.", None
        match = re.search(r'<SUMMARY>(.*?)</SUMMARY>', text, re.DOTALL | re.IGNORECASE)
        if match:
            summary = match.group(1).strip()
            answer = re.sub(r'<SUMMARY>.*?</SUMMARY>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            return answer, summary
        return text, None