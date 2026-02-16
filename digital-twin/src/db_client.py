import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(url, key)

# --- READ OPERATIONS ---

def get_project_risks(project_id):
    """Fetches active risk alerts for the project."""
    # Ensure 'project_risks' table exists in your DB or this will fail
    response = supabase.table("project_risks")\
        .select("*")\
        .eq("project_id", project_id)\
        .order("created_at", desc=True)\
        .limit(10)\
        .execute()
    return response.data

# --- WRITE OPERATIONS ---

def save_risk_alerts(project_id, risks):
    if not risks:
        return
    
    # Clean up old legacy conflicts before inserting new ones to avoid noise
    supabase.table("project_risks")\
        .delete()\
        .eq("project_id", project_id)\
        .eq("risk_type", "Legacy Conflict")\
        .execute()
        
    supabase.table("project_risks").insert(risks).execute()

def update_unit_risk_scores(updates):
    """
    Updates the risk_score column in memory_units.
    NOTE: Ensure you ran 'ALTER TABLE memory_units ADD COLUMN risk_score float;'
    """
    if not updates:
        return
    try:
        for update in updates:
            supabase.table("memory_units") \
                .update({"risk_score": update["risk_score"]}) \
                .eq("project_id", update["project_id"]) \
                .eq("unit_name", update["unit_name"]) \
                .execute()
    except Exception as e:
        print(f"Failed to update risk scores: {e}")

def save_memory_unit(project_id, unit_data):
    payload = {
        "project_id": project_id,
        "unit_name": unit_data["identifier"], # Use the full identifier from the parser
        "unit_type": unit_data.get("type", "unknown"),
        "file_path": unit_data["file_path"],
        "content": unit_data.get("content"),
        "summary": unit_data.get("summary"),
        "code_footprint": unit_data.get("footprint"),
        "embedding": unit_data.get("embedding"),
        "last_modified_at": unit_data.get("last_modified_at"),
        "author_email": unit_data.get("author_email")
    }
    
    # The 'on_conflict' ensures that if the ID exists, we just update the code
    return supabase.table("memory_units").upsert(
        payload, 
        on_conflict="project_id, unit_name" 
    ).execute()

def save_edges(project_id, source_unit_name, targets_list, edge_type="calls"):
    """
    Saves relationships between units.
    Updated to include 'edge_type' (calls, imports, inherits).
    """
    if not targets_list:
        return

    # Optional: Delete existing edges of this type for this source to keep graph clean
    # (Comment this out if you prefer append-only)
    supabase.table("graph_edges")\
        .delete()\
        .eq("project_id", project_id)\
        .eq("source_unit_name", source_unit_name)\
        .eq("edge_type", edge_type)\
        .execute()
        
    edges = []
    for target in targets_list:
        edges.append({
            "project_id": project_id, 
            "source_unit_name": source_unit_name, 
            "target_unit_name": target,
            "edge_type": edge_type
        })
    
    if edges:
        # We use upsert to prevent duplicates if unique constraint exists
        supabase.table("graph_edges").upsert(
            edges, 
            on_conflict="project_id, source_unit_name, target_unit_name, edge_type"
        ).execute()