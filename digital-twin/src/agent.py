import json
import re
import logging
import ast
from typing import List, Dict, Any
from src.services import get_llm_completion
from src.retriever import GraphRetriever
from src.answer_generator import AnswerGenerator
from src.query_processor import QueryProcessor

class LumisAgent:
    def __init__(self, project_id: str, mode: str = "multi-turn", max_steps: int = 4):
        self.project_id = project_id
        self.mode = mode
        self.retriever = GraphRetriever(project_id)
        self.generator = AnswerGenerator(project_id)
        self.query_processor = QueryProcessor()
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

        # --- FIX 1: Process query ONCE before the loop ---
        processed_query = self.query_processor.process(user_query, self.conversation_history)
        print(f"🎯 Intent: {processed_query.intent}")
        if processed_query.pseudocode_hints:
            print(f"💡 Pseudocode Hint Generated")

        for step in range(self.max_steps):
            
            # --- FIX 2: Pass 'processed_query' object instead of raw string ---
            prompt = self._build_step_prompt(processed_query, scratchpad)
            
            # 1. Get LLM response
            response_text = get_llm_completion(
                self._get_system_prompt(), 
                prompt, 
                reasoning_enabled=reasoning_enabled
            )
            
            # 2. Robust Parsing
            data = self._parse_response(response_text, fallback_query=user_query)
            
            thought = data.get("thought", "Analyzing...")
            action = data.get("action")
            confidence = data.get("confidence", 0)
            
            print(f"🤔 Step {step+1} ({confidence}%): {thought}")

            if confidence >= 95 or action == "final_answer":
                break

            if not action or action == "none": 
                print("⚠️ No action generated. Stopping.")
                break
            
            # OPTIONAL: You can inject the rewritten query here if the agent chose 'search_code'
            # but usually it's better to let the agent see the hint in the prompt and decide.
            obs = self._execute_tool(action, data.get("action_input"), collected_elements, scratchpad,processed_query)
            if action == "list_files": repo_structure = obs 

        result = self.generator.generate(
            query=user_query, 
            collected_elements=collected_elements, 
            repo_structure=repo_structure,
            history=self.conversation_history
        )
        self._update_history(user_query, result['answer'])
        return result['answer']

    # --- FIX 3: Update this helper to inject the hints into the LLM's context ---
    def _build_step_prompt(self, processed_query, scratchpad):
        history_text = ""
        if self.conversation_history and len(self.conversation_history) > 0:
            recent_msgs = self.conversation_history[-6:]
            history_text = "CONVERSATION HISTORY:\n" + "\n".join(
                [f"{m['role'].upper()}: {m['content']}" for m in recent_msgs]
            ) + "\n\n"
            
        progress = "\n".join([f"Action: {s['action']} -> {s['observation']}" for s in scratchpad])
        
        # Inject the processor insights
        query_context = f"USER QUERY: {processed_query.original}"
        
        insights = []
        if processed_query.rewritten_query:
             insights.append(f"Search Hint: Try searching for '{processed_query.rewritten_query}'")
        if processed_query.pseudocode_hints:
             insights.append(f"Implementation Hint:\n{processed_query.pseudocode_hints}")
             
        insight_text = "\n\n".join(insights)

        return f"{history_text}{query_context}\n\n{insight_text}\n\nPROGRESS:\n{progress}\n\nNEXT JSON:"

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

    # In src/agent.py -> LumisAgent class

    def _execute_tool(self, action, inp, collected, scratchpad, processed_query=None):
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
                search_input = str(inp)
                
                # If we have a high-quality rewritten query from the processor, 
                # we combine it with the agent's input to maximize recall.
                if processed_query and processed_query.rewritten_query:
                    # Logic: "Agent's specific term" + "Processor's technical keywords"
                    search_input = f"{search_input} {processed_query.rewritten_query}"
                
                # If there are pseudocode hints (for implementation tasks), add them too
                if processed_query and processed_query.pseudocode_hints:
                    search_input += f" {processed_query.pseudocode_hints}"
                
                print(f"🔎 Executing Enhanced Search: {search_input[:100]}...")

                data = self.retriever.search(search_input)
                
                if data:
                    collected.extend(data)
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
                "You are Lumis, a 'Scouting-First' code analysis agent.\n"
                "Your goal is to answer user queries with PRECISE code evidence.\n\n"
                
                "*** CORE WORKFLOW ***\n"
                "1. SCOUT: Use `list_files` or `search_code` to find RELEVANT FILE PATHS. Do not read files randomly.\n"
                "2. VERIFY: Use the provided 'Search Hint' or 'Pseudocode' to refine your search if initial results are poor.\n"
                "3. READ: Only call `read_file` when you are 80%+ sure a file contains the answer.\n"
                "4. ANSWER: Call `final_answer` once you have the code snippets in your context.\n\n"
                
                "*** TOOL USAGE ***\n"
                "- list_files(): Call this FIRST if you don't know the directory structure.\n"
                "- search_code(query): Semantic search for logic/concepts. Use specific technical terms.\n"
                "- read_file(path): Loads the FULL content. Expensive! Use sparingly on targeted files.\n"
                "- final_answer: Delivers the response to the user.\n\n"
                
                "*** RESPONSE FORMAT (Strict JSON) ***\n"
                "{\n"
                "  \"thought\": \"I see the user wants to find auth logic. The file structure shows a 'src/auth' folder...\",\n"
                "  \"confidence\": <0-100>,\n"
                "  \"action\": \"<tool_name>\",\n"
                "  \"action_input\": \"<argument>\"\n"
                "}\n\n"
                "*** CRITICAL OUTPUT RULES ***\n"
                "1. DO NOT output any conversational text, introductions, or explanations.\n"
                "2. Output ONLY the raw JSON object. Do not wrap it in markdown code blocks.\n"
                "3. Ensure the JSON is valid (no trailing commas, double quotes for keys)."
            )

    def _update_history(self, q, a):
        if self.mode == "multi-turn":
            self.conversation_history.append({"role": "user", "content": q})
            self.conversation_history.append({"role": "assistant", "content": a})