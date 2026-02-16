import json
import logging
import re
from typing import List, Dict, Any
from src.services import get_llm_completion
from src.retriever import GraphRetriever
from src.answer_generator import AnswerGenerator

class LumisAgent:
    def __init__(self, project_id: str, mode: str = "multi-turn", max_steps: int = 5):
        self.project_id = project_id
        self.mode = mode
        self.retriever = GraphRetriever(project_id)
        self.generator = AnswerGenerator(project_id)
        self.max_steps = max_steps
        self.conversation_history: List[Dict[str, str]] = []

    def ask(self, user_query: str) -> str:
        if self.mode == "single-turn":
            self.conversation_history = []

        scratchpad = []
        collected_elements: List[Dict[str, Any]] = [] 
        repo_structure = None 
        
        print(f"\n🤖 LUMIS (Adaptive): {user_query}")

        for step in range(self.max_steps):
            # 1. Decide on Action
            prompt = self._build_step_prompt(user_query, scratchpad)
            response_text = get_llm_completion(self._get_system_prompt(), prompt)
            
            # Robust JSON/XML parsing
            data = self._parse_response(response_text)
            
            if not data:
                return f"Error parsing Agent thought. Raw: {response_text}"

            thought = data.get("thought", "Processing...")
            action = data.get("action")
            
            print(f"🤔 Step {step+1}: {thought}")

            # 2. Adaptive Termination Check
            if data.get("final_answer") or action == "final_answer":
                # Generate draft answer
                result = self.generator.generate(
                    query=user_query, 
                    collected_elements=collected_elements, 
                    repo_structure=repo_structure,
                    history=self.conversation_history
                )

                # Verification: Did we actually find the answer?
                if "I could not find" in result['answer'] and step < self.max_steps - 2:
                    print("   ⚠️ Insight: Answer incomplete. Continuing investigation...")
                    scratchpad.append({
                        "thought": "The previous info was insufficient. I need to try a different approach.",
                        "action": "retry",
                        "observation": "Draft answer failed. Search for broader terms or list files."
                    })
                    continue
                else:
                    self._update_history(user_query, result['answer'])
                    return result['answer']

            # 3. Execute Tools
            obs = self._execute_tool(action, data.get("action_input"), collected_elements, scratchpad)
            if action == "list_files": repo_structure = obs

        return "I ran out of steps without finding a complete answer."

    def _execute_tool(self, action, inp, collected, scratchpad):
        obs = "Error: Unknown tool"
        
        if action == "list_files":
            files = self.retriever.list_all_files()
            if not files:
                obs = "Observation: No files found in this project. Is the repository indexed?"
            else:
                obs = f"Observation: Found {len(files)} files. Top files: " + ", ".join(files[:100])
        elif action == "read_file":
            # Fix: Handle case where input might be a list or multiline string
            path = inp.strip()
            data = self.retriever.fetch_file_content(path)
            if data: 
                collected.extend(data)
                unit_names = [d['unit_name'] for d in data]
                obs = f"Read {len(data)} units from {path}: {', '.join(unit_names)}"
            else:
                obs = f"Read {path}: File empty or not found."

        elif action == "search_code":
            data = self.retriever.search(inp)
            if data: collected.extend(data)
            obs = f"Found {len(data)} matches."
            
        scratchpad.append({"thought": "Executed tool", "action": f"{action}({inp})", "observation": obs})
        return obs

    def _get_system_prompt(self) -> str:
        return (
            "You are Lumis. Find code to answer the user.\n"
            "TOOLS:\n"
            "1. list_files(): See file structure.\n"
            "2. read_file(path): Read content of a specific file.\n"
            "3. search_code(query): Search for functions/logic.\n\n"
            "IMPORTANT: Respond in strict JSON format.\n"
            "Example: {\"thought\": \"Checking file structure\", \"action\": \"list_files\", \"action_input\": \"\"}\n"
            "Example: {\"thought\": \"Reading api.py\", \"action\": \"read_file\", \"action_input\": \"api.py\"}\n"
            "When done, use {\"action\": \"final_answer\"}."
        )

    def _build_step_prompt(self, query, scratchpad):
        trace = "\n".join([f"Act: {s['action']} | Res: {s['observation']}" for s in scratchpad])
        return f"QUERY: {query}\nLOG:\n{trace}\nNext JSON:"

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Tries JSON first, then falls back to XML tool parsing."""
        # 1. Try standard JSON extraction
        clean_text = text.replace("```json", "").replace("```", "").strip()
        json_match = re.search(r'(\{.*\})', clean_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # 2. Fallback: Parse XML Tool Calls (e.g. <function=read_file>...)
        # We only take the FIRST tool call found to avoid complex multi-threading logic
        func_match = re.search(r'<function=(.*?)>', text)
        if func_match:
            action = func_match.group(1).strip()
            # Extract parameter. Pattern: <parameter=path>value</parameter>
            # We match ANY parameter name since models vary (path, query, etc.)
            param_match = re.search(r'<parameter=.*?>(.*?)</parameter>', text, re.DOTALL)
            action_input = param_match.group(1).strip() if param_match else ""
            
            return {
                "thought": "Parsed from XML tool call",
                "action": action,
                "action_input": action_input
            }
            
        # 3. Last Resort: Simple Keyword Matching
        if "list_files" in text:
            return {"thought": "Auto-recovery", "action": "list_files", "action_input": ""}
            
        return None

    def _update_history(self, q, a):
        if self.mode == "multi-turn":
            self.conversation_history.append({"role": "user", "content": q})
            self.conversation_history.append({"role": "assistant", "content": a})