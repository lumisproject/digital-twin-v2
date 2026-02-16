import json
import logging
import re
from typing import List, Dict, Any
from src.services import get_llm_completion
from src.retriever import GraphRetriever
from src.answer_generator import AnswerGenerator

class LumisAgent:
    def __init__(self, project_id: str, mode: str = "multi-turn", max_steps: int = 10):
        self.project_id = project_id
        self.mode = mode
        self.retriever = GraphRetriever(project_id)
        self.generator = AnswerGenerator(project_id)
        # Increased steps to allow reading multiple files
        self.max_steps = max_steps 
        self.conversation_history: List[Dict[str, str]] = []

    def ask(self, user_query: str) -> str:
        if self.mode == "single-turn":
            self.conversation_history = []

        scratchpad = []
        collected_elements: List[Dict[str, Any]] = [] 
        repo_structure_context = None 
        
        print(f"\n🤖 LUMIS AGENT ({self.mode.upper()}): {user_query}")

        for step in range(self.max_steps):
            prompt = self._build_step_prompt(user_query, scratchpad)
            response_text = get_llm_completion(self._get_system_prompt(), prompt)
            
            try:
                clean_response = self._clean_json(response_text)
                response_data = json.loads(clean_response)
            except Exception:
                response_data = self._manual_recovery(response_text)
                if not response_data:
                    return f"Reasoning error: Raw response: {response_text}"

            thought = response_data.get("thought", "Thinking...")
            action = response_data.get("action")
            final_answer_trigger = response_data.get("final_answer")

            print(f"🤔 Step {step+1}: {thought}")

            # --- END CONDITION ---
            if final_answer_trigger or (step == self.max_steps - 1):
                # Pass all collected blocks to the Generator
                gen_result = self.generator.generate(
                    query=user_query, 
                    collected_elements=collected_elements, 
                    repo_structure=repo_structure_context,
                    history=self.conversation_history
                )
                
                answer = gen_result['answer']
                if self.mode == "multi-turn":
                    self.conversation_history.append({"role": "user", "content": user_query})
                    self.conversation_history.append({"role": "assistant", "content": answer})
                return answer

            # --- TOOL EXECUTION ---
            if action == "list_files":
                files = self.retriever.list_all_files()
                repo_structure_context = ", ".join(files)
                display_files = files[:50] 
                obs = f"Found {len(files)} files: " + ", ".join(display_files)
                scratchpad.append({"thought": thought, "action": "list_files", "observation": obs})

            elif action == "read_file":
                target_file = response_data.get("action_input", "")
                # Fetch all blocks for this file
                file_blocks = self.retriever.fetch_file_content(target_file)
                
                if file_blocks:
                    collected_elements.extend(file_blocks)
                    # Extract unit names for the observation (to save tokens in the prompt)
                    unit_names = [b['unit_name'] for b in file_blocks]
                    obs = f"Read {target_file}. Found {len(file_blocks)} units: {', '.join(unit_names)}"
                else:
                    obs = f"Read {target_file}. File is empty or not indexed."
                
                scratchpad.append({"thought": thought, "action": f"read_file({target_file})", "observation": obs})

            elif action == "search_code":
                query_term = response_data.get("action_input", "")
                results = self.retriever.search(query_term, limit=5)
                collected_elements.extend(results)
                
                found_summaries = [f"{r['file_path']}::{r['unit_name']}" for r in results]
                obs = f"Found {len(results)} matches: {', '.join(found_summaries)}"
                scratchpad.append({"thought": thought, "action": f"search({query_term})", "observation": obs})
            
            else:
                scratchpad.append({"thought": thought, "action": action, "observation": "Error: Unknown tool."})

        return "I hit my step limit."

    def _get_system_prompt(self) -> str:
        return (
            "You are Lumis Scout. Your goal is to navigate the codebase to find information.\n"
            "TOOLS:\n"
            "1. `list_files()`: Returns all file paths. Use FIRST to understand repo structure.\n"
            "2. `read_file(file_path)`: Returns ALL functions/classes in a specific file. Use this for 'List all functions' requests.\n"
            "3. `search_code(query)`: Semantic search. Use this for 'How does X work?' questions.\n\n"
            "STRATEGY:\n"
            "- If user asks 'List all functions', call `list_files`, then `read_file` for each relevant source file.\n"
            "- Gather enough information, then output `\"final_answer\": true`.\n"
            "FORMAT: Respond in pure JSON.\n"
            'Example: {"thought": "I will read the api file.", "action": "read_file", "action_input": "src/api.py"}'
        )

    def _build_step_prompt(self, query, scratchpad):
        history = ""
        if self.conversation_history:
             history = "CONVERSATION HISTORY:\n" + "\n".join([f"{m['role']}: {m['content']}" for m in self.conversation_history]) + "\n\n"
        
        trace = "\n".join([f"Step: {s['thought']}\nAction: {s['action']}\nResult: {s['observation']}\n" for s in scratchpad])
        
        return (
            f"{history}"
            f"CURRENT QUERY: {query}\n\n"
            f"YOUR INVESTIGATION LOG:\n{trace}\n\n"
            "Based on the log, what is your next step? (JSON ONLY)"
        )

    def _clean_json(self, text):
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match: return match.group(1)
        return text

    def _manual_recovery(self, text):
        if "list_files" in text:
            return {"thought": "Auto-recovery: Listing files.", "action": "list_files", "action_input": ""}
        if "read_file" in text:
            match = re.search(r"read_file\(['\"](.*?)['\"]\)", text)
            path = match.group(1) if match else ""
            return {"thought": "Auto-recovery: Reading file.", "action": "read_file", "action_input": path}
        if "search_code" in text:
            match = re.search(r"search_code\(['\"](.*?)['\"]\)", text)
            query = match.group(1) if match else "main"
            return {"thought": "Auto-recovery: Searching code.", "action": "search_code", "action_input": query}
        return {"thought": "I have enough info.", "final_answer": True}