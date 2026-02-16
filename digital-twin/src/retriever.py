import logging
import json
from typing import List, Dict, Any
from src.db_client import supabase
from src.services import get_embedding, get_llm_completion

class GraphRetriever:
    """
    Advanced Retriever implementing Phase 1 & 2 of the FastCode architecture.
    Features: Hybrid Search, Query Augmentation, and Graph Expansion.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.logger = logging.getLogger(__name__)

    def list_all_files(self) -> List[str]:
        response = supabase.table("memory_units").select("file_path").eq("project_id", self.project_id).execute()
        if not response.data: return []
        return sorted(list(set([item['file_path'] for item in response.data])))

    def fetch_file_content(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            response = supabase.table("memory_units")\
                .select("id, unit_name, unit_type, content, file_path, summary")\
                .eq("project_id", self.project_id)\
                .eq("file_path", file_path)\
                .execute()
            return response.data if response.data else []
        except Exception as e:
            self.logger.error(f"Error fetching file: {e}")
            return []

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Hybrid Search: Combines Semantic (Vector) and Sparse (BM25/Keyword) search.
        """
        try:
            # 1. Generate Vector
            query_vector = get_embedding(query)
            
            # 2. Prepare Params for Hybrid Search
            params = {
                "query_embedding": query_vector,
                "query_text": query, 
                "match_threshold": 0.3,
                "match_count": limit,
                "filter_project_id": self.project_id
            }
            
            # 3. Call the new Hybrid RPC function
            rpc_response = supabase.rpc("match_code_hybrid", params).execute()
            
            hits = rpc_response.data if rpc_response.data else []
            
            # 4. Deduplicate results
            seen = set()
            unique_hits = []
            for hit in hits:
                if hit['id'] not in seen:
                    seen.add(hit['id'])
                    unique_hits.append(hit)
            
            return unique_hits
            
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return []

    def _augment_query(self, user_query: str) -> str:
        """Uses LLM to expand short queries into technical search terms."""
        system_prompt = "You are a query optimizer. Convert the user's question into a specific keyword-rich search query for code. Output ONLY the query."
        # Fast one-shot call
        suggestion = get_llm_completion(system_prompt, f"Question: {user_query}\nBetter Search Query:")
        return suggestion if suggestion else user_query

    def _hybrid_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        try:
            vector = get_embedding(query)
            params = {
                "query_embedding": vector,
                "query_text": query, # Passed for BM25
                "match_threshold": 0.1, # Lower threshold because BM25 helps filter
                "match_count": limit,
                "filter_project_id": self.project_id
            }
            # Call the NEW SQL function
            response = supabase.rpc("match_code_hybrid", params).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Hybrid search failed: {e}")
            return []

    def _expand_graph(self, initial_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Finds immediate neighbors (dependencies) of the hits."""
        source_names = [h['unit_name'] for h in initial_hits]
        
        # Find outgoing edges (What do these functions call?)
        edges = supabase.table("graph_edges")\
            .select("target_unit_name")\
            .eq("project_id", self.project_id)\
            .in_("source_unit_name", source_names)\
            .limit(10)\
            .execute()
        
        if not edges.data:
            return initial_hits

        target_names = [e['target_unit_name'] for e in edges.data]
        
        # Fetch content of these dependencies
        neighbors = supabase.table("memory_units")\
            .select("id, unit_name, unit_type, content, file_path, summary")\
            .eq("project_id", self.project_id)\
            .in_("unit_name", target_names)\
            .limit(5)\
            .execute()
            
        combined = initial_hits + (neighbors.data if neighbors.data else [])
        
        # Deduplicate
        seen = set()
        unique = []
        for node in combined:
            if node['id'] not in seen:
                seen.add(node['id'])
                unique.append(node)
                
        return unique