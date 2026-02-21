import re
import logging
import traceback
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
        self.logger.info("Generating answer")
        
        try:
            # 1. Format the Context
            context_str = self._prepare_context(collected_elements)
            
            # Safety Fallback: Truncate context if it gets absurdly long (~100k chars is roughly 25k tokens)
            max_context_chars = 100000 
            if len(context_str) > max_context_chars:
                self.logger.warning(f"Context too long ({len(context_str)} chars). Truncating.")
                context_str = context_str[:max_context_chars] + "\n\n...[Context truncated due to length]..."
            
            structure_context = ""
            if repo_structure:
                structure_context = f"**REPOSITORY STRUCTURE**:\n{repo_structure}\n\n"

            # 2. Define Base System Prompt (Core Identity & Rules)
            base_system_prompt = (
                "You are Lumis, an intelligent Code Analysis Agent. Your goal is to satisfy the user's request "
                "using ONLY the provided code snippets. Do NOT guess or invent logic.\n\n"
                "Guidelines:\n"
                "1. Focus primarily on answering the question itself.\n"
                "2. The provided code/file content may be irrelevant to the original question or may contain noise. In this case, do not rely on the provided fragment.\n"
                "3. Provide clear, accurate, and concise answers.\n"
                "4. Reference specific code snippets when relevant.\n"
                "5. Include file paths and corresponding code snippets when discussing specific code.\n"
                "6. If the provided context doesn't contain enough information, say so.\n"
                "7. Use code examples to illustrate your explanations.\n"
                "8. Be technical but accessible.\n"
                "9. If asked to find something, list all relevant locations.\n"
                "10. When comparing code from different files, clearly distinguish between them.\n"
                "11. **IMPORTANT: Always respond in the same language as the user's question.**"
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

Missing Information:
- [description of what files or context are still needed]
- [why this information would be helpful]

Key Facts:
- [fact 1]

Symbol Mappings:
- [user term] -> [actual symbol in codebase]
</SUMMARY>

**STRICT FORMAT REQUIREMENT**: You MUST output the summary exactly in the above `<SUMMARY>...</SUMMARY>` structure. Do NOT place content outside the tags. Regardless of the language you use to respond, always use `<SUMMARY>...</SUMMARY>` as the summary tags."""
                
                # For multi-turn, the system prompt handles the summary instruction.
                user_summary_instruction = ""
                
            else:
                # Fallback for single-turn or no history
                system_prompt = base_system_prompt + "\n\n**INTERNAL SUMMARY**: End with a hidden <SUMMARY> block analyzing the findings."
                user_summary_instruction = "- End with <SUMMARY>Files Analyzed; Evidence Found</SUMMARY>"

            # 4. Build the User Prompt
            history_text = ""
            if history:
                recent = history[-6:] # Keep the context recent to avoid huge prompts
                history_text = "**PREVIOUS CONVERSATION**:\n" + "\n".join([f"{m['role'].upper()}: {m['content']}" for m in recent]) + "\n\n---\n"

            user_prompt = (
                f"{history_text}"
                f"**USER QUERY**: {query}\n\n"
                f"{structure_context}"
                f"**RETRIEVED CODE**:\n{context_str}\n\n"
                "**INSTRUCTIONS**:\n"
                "- Please answer the question using the code snippets above only if they are relevant.\n"
                "- Fulfill the query exactly as written.\n"
                "- Cite sources using brackets, e.g., [src/main.py].\n"
                f"{user_summary_instruction}"
            )
            
            # 5. Execute
            raw_response = get_llm_completion(system_prompt, user_prompt)
            
            if not raw_response:
                raise ValueError("Received empty response from the LLM.")
                
            answer, summary = self._parse_response_with_summary(raw_response)
            
            # 6. Fallback: Generate summary if parsing failed
            if self.enable_multi_turn and not summary:
                self.logger.info("Generating fallback summary from retrieved elements")
                summary = self._generate_fallback_summary(query, answer, collected_elements)
            
            return {
                "answer": answer,
                "summary": summary,
                "sources": [e.get('file_path', 'unknown') for e in collected_elements]
            }
            
        except Exception as e:
            self.logger.error(f"Failed to generate answer: {e}")
            full_error = traceback.format_exc()
            self.logger.error(f"Full error traceback:\n{full_error}")
            
            # Graceful failure response
            return {
                "answer": f"Error generating answer: {str(e)}. Please check the logs or try rephrasing.",
                "summary": "Error occurred during generation.",
                "sources": [e.get('file_path', 'unknown') for e in collected_elements]
            }

    def _prepare_context(self, elements: List[Dict[str, Any]]) -> str:
        if not elements:
            return "NO CODE SNIPPETS RETRIEVED."
        
        seen = set()
        parts = []
        for i, elem in enumerate(elements, 1):
            content = elem.get('content', '')
            content_hash = hash(content)
            
            if content_hash not in seen:
                seen.add(content_hash)
                
                # Truncate extremely long single files
                if len(content) > 50000:
                    content = content[:50000] + "\n... (truncated)"
                    
                file_path = elem.get('file_path', 'unknown')
                unit_name = elem.get('unit_name', 'unknown')
                
                parts.append(f"### Code Snippet {i}\n**File**: `{file_path}`\n**Unit**: `{unit_name}`\n```python\n{content}\n```")
        
        return "\n\n---\n\n".join(parts)

    def _parse_response_with_summary(self, text: str) -> Tuple[str, Optional[str]]:
        """Robustly extract summary using multiple regex patterns."""
        if not text: 
            return "Error: No response.", None
            
        # Try multiple patterns for robust summary extraction
        summary_patterns = [
            r'<\s*[Ss][Uu][Mm][Mm][Aa][Rr][Yy]\s*:?\s*>(.*?)<\s*/\s*[Ss][Uu][Mm][Mm][Aa][Rr][Yy]\s*>',
            r'\*\*\s*<\s*[Ss][Uu][Mm][Mm][Aa][Rr][Yy]\s*>\s*\*\*(.*?)\*\*\s*<\s*/\s*[Ss][Uu][Mm][Mm][Aa][Rr][Yy]\s*>\s*\*\*'
        ]

        for pattern in summary_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                summary = match.group(1).strip()
                answer = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
                return answer, summary

        # Fallback explicit split if regex somehow fails but tags are present
        if "<SUMMARY>" in text.upper() and "</SUMMARY>" in text.upper():
            try:
                parts = re.split(r'<\s*/?\s*[Ss][Uu][Mm][Mm][Aa][Rr][Yy]\s*>', text, flags=re.IGNORECASE)
                if len(parts) >= 3:
                    return parts[0].strip(), parts[1].strip()
            except:
                pass

        self.logger.warning("No summary found in response.")
        return text, None

    def _generate_fallback_summary(self, query: str, answer: str, retrieved_elements: List[Dict[str, Any]]) -> str:
        """Generates a fallback summary for internal tracking when LLM misses the tags."""
        summary_parts = ["Fallback Summary Generated:"]

        # 1. Add files read section
        files_read = set(e.get('file_path') for e in retrieved_elements if e.get('file_path'))
        if files_read:
            summary_parts.append("\nFiles Read:")
            for file_path in sorted(files_read)[:10]:
                summary_parts.append(f"- {file_path}")
        else:
            summary_parts.append("\nFiles Read: None")

        # 2. Add query context
        summary_parts.append(f"\nQuery: {query[:200]}") 
        
        # 3. Add answer preview
        answer_preview = answer[:150].replace("\n", " ").strip()
        if len(answer) > 150:
            answer_preview += "..."
        summary_parts.append(f"Answer Preview: {answer_preview}")

        return "\n".join(summary_parts)