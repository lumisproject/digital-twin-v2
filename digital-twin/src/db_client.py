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

def get_unit_footprint(project_id, unit_name):
    """Checks if a unit already exists and returns its hash to prevent overwrites."""
    try:
        res = supabase.table("memory_units")\
            .select("code_footprint")\
            .eq("project_id", project_id)\
            .eq("unit_name", unit_name)\
            .limit(1)\
            .execute()
        return res.data[0]['code_footprint'] if res.data else None
    except Exception:
        return None

def get_project_data(project_id):
    """Fetches the entire graph for risk analysis."""
    units_resp = supabase.table("memory_units")\
        .select("unit_name, file_path, last_modified_at, content, risk_score")\
        .eq("project_id", project_id).execute()
    
    edges_resp = supabase.table("graph_edges")\
        .select("source_unit_name, target_unit_name")\
        .eq("project_id", project_id).execute()
        
    return units_resp.data or [], edges_resp.data or []

def get_project_risks(project_id):
    response = supabase.table("project_risks")\
        .select("*")\
        .eq("project_id", project_id)\
        .order("created_at", desc=True)\
        .execute()
    return response.data if response.data else []

# --- WRITE OPERATIONS ---

def save_edges(project_id, source_unit_name, targets_list, edge_type="calls"):
    # Kept for backward compatibility
    edges = [{
        "project_id": project_id, 
        "source_unit_name": source_unit_name, 
        "target_unit_name": target,
        "edge_type": edge_type
    } for target in targets_list]
    save_edges(project_id, edges)

# --- FASTCODE OPTIMIZATION: BULK WRITE OPERATIONS ---

def save_memory_units(project_id, units_data_list):
    """Upserts multiple memory units in a single network transaction."""
    if not units_data_list: return
    
    payloads = []
    for unit_data in units_data_list:
        payloads.append({
            "project_id": project_id,
            "unit_name": unit_data["identifier"],
            "unit_type": unit_data.get("type", "unknown"),
            "file_path": unit_data["file_path"],
            "content": unit_data.get("content"),
            "summary": unit_data.get("summary"),
            "code_footprint": unit_data.get("footprint"),
            "embedding": unit_data.get("embedding"),
            "last_modified_at": unit_data.get("last_modified_at"),
            "author_email": unit_data.get("author_email")
        })
    
    # Supabase handles list upserts natively
    return supabase.table("memory_units").upsert(
        payloads, on_conflict="project_id, unit_name"
    ).execute()

def save_edges(project_id, edges_list):
    """Inserts multiple graph edges in a single network transaction."""
    if not edges_list: return
    
    # We clear out old edges for the sources being updated to handle differential sync cleanly
    source_units = list(set([edge["source_unit_name"] for edge in edges_list]))
    
    if source_units:
        # Delete old edges for the modified units before bulk inserting new ones
        supabase.table("graph_edges")\
            .delete()\
            .eq("project_id", project_id)\
            .in_("source_unit_name", source_units)\
            .execute()
            
    supabase.table("graph_edges").insert(edges_list).execute()

def save_risk_alerts(project_id, risks):
    if not risks: return
    supabase.table("project_risks").delete().eq("project_id", project_id).eq("risk_type", "Legacy Conflict").execute()
    supabase.table("project_risks").insert(risks).execute()

def update_unit_risk_scores(updates):
    if not updates: return
    for update in updates:
        supabase.table("memory_units")\
            .update({"risk_score": update["risk_score"]})\
            .eq("project_id", update["project_id"])\
            .eq("unit_name", update["unit_name"])\
            .execute()