import json
import re
import logging
import ast
from typing import List, Dict, Any
from src.services import get_llm_completion
from src.retriever import GraphRetriever
from src.answer_generator import AnswerGenerator

class LumisAgent:
    def __init__(self, project_id: str, mode: str = "multi-turn", max_steps: int = 4):
        self.project_id = project_id
        self.mode = mode
        self.retriever = GraphRetriever(project_id)
        self.generator = AnswerGenerator(project_id)
        self.max_steps = max_steps
        self.conversation_history: List[Dict[str, str]] = []
        self.logger = logging.getLogger(__name__)

    def ask(self, user_query: str, reasoning_enabled: bool = False) -> str:
        print(self.mode)
        if self.mode == "single-turn":
            self.conversation_history = []

        scratchpad = []
        collected_elements: List[Dict[str, Any]] = [] 
        repo_structure = None 
        
        print(f"\n🤖 LUMIS: {user_query}")

        for step in range(self.max_steps):
            # FIX: Pass conversation history to the prompt builder
            prompt = self._build_step_prompt(user_query, scratchpad)
            
            # 1. Get LLM response
            response_text = get_llm_completion(
                self._get_system_prompt(), 
                prompt, 
                reasoning_enabled=reasoning_enabled
            )
            
            # 2. Robust Parsing with Fallback
            # Pass user_query so we can default to searching if parsing fails
            data = self._parse_response(response_text, fallback_query=user_query)
            
            thought = data.get("thought", "Analyzing...")
            action = data.get("action")
            confidence = data.get("confidence", 0)
            
            print(f"🤔 Step {step+1} ({confidence}%): {thought}")

            # 3. Smart Termination
            if confidence >= 85 or action == "final_answer":
                break

            # 4. Tool Execution
            if not action or action == "none": 
                print("⚠️ No action generated. Stopping.")
                break
                
            obs = self._execute_tool(action, data.get("action_input"), collected_elements, scratchpad)
            if action == "list_files": repo_structure = obs

        # Generate final answer with whatever was found
        result = self.generator.generate(
            query=user_query, 
            collected_elements=collected_elements, 
            repo_structure=repo_structure,
            history=self.conversation_history
        )
        self._update_history(user_query, result['answer'])
        return result['answer']

    def _parse_response(self, text: str, fallback_query: str = "") -> Dict[str, Any]:
        """
        Robustly extracts JSON. If extraction fails, creates a fallback action 
        based on the text content to keep the agent alive.
        """
        if not text: 
            return self._create_fallback(fallback_query, "Empty response from LLM")

        # 1. Try to find JSON block
        clean_text = text.replace("```json", "").replace("```", "").strip()
        start_idx = clean_text.find('{')
        end_idx = clean_text.rfind('}')

        if start_idx != -1 and end_idx != -1:
            try:
                json_str = clean_text[start_idx:end_idx + 1]
                # Fix common LLM syntax errors before parsing
                json_str = self._sanitize_json_string(json_str)
                return json.loads(json_str)
            except Exception as e:
                print(f"⚠️ JSON extract failed: {e}")
        
        # 2. Python-dict Fallback (handling single quotes)
        try:
            if start_idx != -1 and end_idx != -1:
                return ast.literal_eval(clean_text[start_idx:end_idx + 1])
        except:
            pass

        # 3. Ultimate Fallback: Treat the text as a thought and force a search
        # This fixes "I'll help you find..." causing a crash.
        return self._create_fallback(fallback_query, text[:200])

    def _create_fallback(self, query: str, thought_snippet: str) -> Dict[str, Any]:
        """Creates a default search action when parsing fails."""
        return {
            "thought": f"Parsing failed. Falling back to search. Raw: {thought_snippet}...",
            "action": "search_code",
            "action_input": query,
            "confidence": 50
        }

    def _sanitize_json_string(self, json_str: str) -> str:
        """Fixes common JSON format errors."""
        # Remove comments
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        # Fix trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        return json_str

    def _execute_tool(self, action, inp, collected, scratchpad):
        obs = "No results."
        try:
            if action == "list_files":
                files = self.retriever.list_all_files()
                obs = f"Repo contains {len(files)} files. First 50: {', '.join(files[:50])}"
            elif action == "read_file":
                path = str(inp).strip()
                data = self.retriever.fetch_file_content(path)
                if data:
                    collected.extend(data)
                    obs = f"Successfully read {path}."
                else:
                    obs = f"Error: File {path} not found in database. Check spelling or use list_files."
            elif action == "search_code":
                data = self.retriever.search(str(inp))
                if data:
                    collected.extend(data)
                    # Deduplicate found files for the observation log
                    found_files = list(set([d['file_path'] for d in data]))
                    obs = f"Found {len(data)} matches in: {', '.join(found_files[:10])}"
                else:
                    obs = f"No results found for '{inp}'. Try broader keywords."
        except Exception as e:
            obs = f"Tool Error: {str(e)}"
            
        scratchpad.append({"thought": "System Result", "action": f"{action}({inp})", "observation": obs})
        return obs

    def _get_system_prompt(self) -> str:
        return (
            "You are Lumis, a code analysis agent. Find ACTUAL code to answer the user.\n"
            "TOOLS:\n"
            "1. list_files(): Use this if you don't know file paths.\n"
            "2. read_file(path): Read full content of a specific file.\n"
            "3. search_code(query): Search for code snippets (functions, classes).\n"
            "4. final_answer: Call this when you have found enough code.\n\n"
            "RESPONSE FORMAT (JSON ONLY):\n"
            "{\n"
            "  \"thought\": \"reasoning...\",\n"
            "  \"confidence\": 0-100,\n"
            "  \"action\": \"tool_name\",\n"
            "  \"action_input\": \"parameter\"\n"
            "}\n"
            "RULE: If you cannot find the answer after searching, try 'list_files' to see if you have the wrong paths."
        )

    def _build_step_prompt(self, query, scratchpad):
        # FIX: Include conversation history for context-aware reasoning
        history_text = ""
        if self.conversation_history and len(self.conversation_history) > 0:
            # Use last 6 messages to keep context relevant but concise
            recent_msgs = self.conversation_history[-6:]
            history_text = "CONVERSATION HISTORY:\n" + "\n".join(
                [f"{m['role'].upper()}: {m['content']}" for m in recent_msgs]
            ) + "\n\n"
            
        progress = "\n".join([f"Action: {s['action']} -> {s['observation']}" for s in scratchpad])
        return f"{history_text}USER QUERY: {query}\n\nPROGRESS:\n{progress}\n\nNEXT JSON:"

    def _update_history(self, q, a):
        if self.mode == "multi-turn":
            self.conversation_history.append({"role": "user", "content": q})
            self.conversation_history.append({"role": "assistant", "content": a})