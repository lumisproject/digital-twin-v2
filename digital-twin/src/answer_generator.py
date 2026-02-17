import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from src.services import get_llm_completion

class AnswerGenerator:
    """
    Generates evidence-based answers. Strictly forbids guessing architecture from file names.
    """
    def __init__(self, project_id: str, enable_multi_turn: bool = True):
        self.project_id = project_id
        self.enable_multi_turn = enable_multi_turn
        self.logger = logging.getLogger(__name__)

    def generate(self, query: str, collected_elements: List[Dict[str, Any]], repo_structure: str = None, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        
        # 1. Format the Context
        context_str = self._prepare_context(collected_elements)
        
        structure_context = ""
        if repo_structure:
            structure_context = f"REPOSITORY STRUCTURE:\n{repo_structure}\n\n"

        # 2. Define Base System Prompt (Core Identity & Rules)
        base_system_prompt = (
            "You are Lumis, an intelligent Code Analysis Agent. Your goal is to satisfy the user's request "
            "using ONLY the provided code snippets. Do NOT guess or invent logic.\n\n"
            "MISSION ADAPTIVITY:\n"
            "1. IDENTIFY INTENT: Determine if the user wants code retrieval, a technical explanation, or architectural advice.\n"
            "2. RETRIEVAL STYLE: If the user asks for specific code/logic (e.g., 'get', 'show', 'provide'), output the code VERBATIM "
            "in markdown blocks. Keep explanations to an absolute minimum.\n"
            "3. ANALYSIS STYLE: If the user asks 'how', 'why', or for a summary, provide a deep architectural explanation "
            "citing variables and dependencies.\n"
            "4. PRECISION: If multiple code blocks are provided but only one is relevant, focus ONLY on the relevant one.\n"
        )

        # 3. Dynamic Prompting: Multi-turn vs Single-turn
        if self.enable_multi_turn and history:
            system_prompt = base_system_prompt + """
            **Multi-turn Dialogue Instructions:**
            At the end of your answer, you MUST provide a structured summary for internal use (not shown to the user).
            The summary should be enclosed in <SUMMARY> tags and include:
            1. Intent: A sentence describing the user's intent in this turn
            2. Files Read: List all the files you have analyzed in this conversation
            3. Missing Information: Describe what additional files, classes, functions, or context would help answer the query more completely
            4. Key Facts: Stable conclusions that can be relied upon in subsequent turns
            5. Symbol Mappings: Map user-mentioned names to actual symbols (e.g., "the function" -> "utils.process_data")

            **IMPORTANT**: Keep the summary under 500 words. Focus on information that helps with code location and reasoning.

            Format:
            <SUMMARY>
            Files Read:
            - [repo_name/file_path_1] - [brief description of what was found]
            - [repo_name/file_path_2] - [brief description of what was found]

            Missing Information:
            - [description of what files or context are still needed]
            - [why this information would be helpful]

            Key Facts:
            - [fact 1]
            - [fact 2]

            Symbol Mappings:
            - [user term] -> [actual symbol in codebase]
            </SUMMARY>

            **STRICT FORMAT REQUIREMENT**: You MUST output the summary exactly in the above `<SUMMARY>...</SUMMARY>` structure. Do NOT place content outside the tags. Regardless of the language you use to respond, always use `<SUMMARY>...</SUMMARY>` as the summary tags."""
            
            # For multi-turn, the system prompt handles the summary instruction.
            user_summary_instruction = ""
            
        else:
            # Fallback for single-turn or no history
            system_prompt = base_system_prompt + "\n4. INTERNAL SUMMARY: End with a hidden <SUMMARY> block analyzing the findings."
            user_summary_instruction = "- End with <SUMMARY>Files Analyzed; Evidence Found</SUMMARY>"

        # 4. Build the User Prompt
        history_text = ""
        if history:
            recent = history[-6:]
            history_text = "PREVIOUS CONVERSATION:\n" + "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent]) + "\n\n"

        user_prompt = (
            f"{history_text}"
            f"USER QUERY: {query}\n\n"
            f"{structure_context}"
            f"RETRIEVED CODE:\n{context_str}\n\n"
            "INSTRUCTIONS:\n"
            "- Fulfill the query exactly as written.\n"
            "- Cite sources using brackets, e.g., [src/main.py].\n"
            f"{user_summary_instruction}"
        )
        
        # 5. Execute
        raw_response = get_llm_completion(system_prompt, user_prompt)
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
        # Robust regex to capture content inside <SUMMARY> tags (dotall + ignorecase)
        match = re.search(r'<SUMMARY>(.*?)</SUMMARY>', text, re.DOTALL | re.IGNORECASE)
        if match:
            summary = match.group(1).strip()
            # Remove the summary block from the final answer shown to user
            answer = re.sub(r'<SUMMARY>.*?</SUMMARY>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            return answer, summary
        return text, None