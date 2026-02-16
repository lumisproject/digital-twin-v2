import logging
from typing import List, Dict, Any
from src.db_client import supabase
from src.services import get_embedding

class GraphRetriever:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.logger = logging.getLogger(__name__)

    def list_all_files(self) -> List[str]:
        """Returns all unique file paths."""
        response = supabase.table("memory_units")\
            .select("file_path")\
            .eq("project_id", self.project_id)\
            .execute()
        
        if not response.data: 
            return []
        return sorted(list(set([item['file_path'] for item in response.data])))

    def fetch_file_content(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Retrieves all code blocks (functions/classes) for a specific file.
        This is crucial for questions like 'List all functions in main.py'.
        """
        try:
            response = supabase.table("memory_units")\
                .select("id, unit_name, unit_type, content, file_path, summary")\
                .eq("project_id", self.project_id)\
                .eq("file_path", file_path)\
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            self.logger.error(f"Error fetching file content: {e}")
            return []

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Vector search for semantic discovery."""
        try:
            query_vector = get_embedding(query)
            params = {
                "query_embedding": query_vector,
                "match_threshold": 0.3,
                "match_count": limit,
                "filter_project_id": self.project_id
            }
            rpc_response = supabase.rpc("match_code_sections", params).execute()
            
            hits = rpc_response.data if rpc_response.data else []
            
            # Simple deduplication by ID
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