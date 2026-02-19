import os
import git
import time
from datetime import datetime, timezone # <-- ADDED IMPORT
from tree_sitter_language_pack import get_parser
from src.services import get_llm_completion, get_embedding, generate_footprint
from src.db_client import supabase, save_memory_unit, save_edges, get_unit_footprint
from src.indexing.parser import AdvancedCodeParser
from src.risk_engine import calculate_predictive_risks

# <-- REPLACED get_git_metadata WITH get_function_metadata
def get_function_metadata(repo_path, file_path, start_line, end_line, repo_obj):
    """Uses git blame to find the last time specific lines of a function were modified."""
    try:
        rel_path = os.path.relpath(file_path, repo_path)
        
        # Tree-sitter is 0-indexed, git blame is 1-indexed
        s_line = max(1, start_line + 1)
        e_line = max(s_line, end_line + 1) 
        
        blame = repo_obj.blame('HEAD', rel_path, L=f'{s_line},{e_line}')
        
        latest_commit = None
        for commit, _ in blame:
            if not latest_commit or commit.committed_datetime > latest_commit.committed_datetime:
                latest_commit = commit
                
        if not latest_commit: 
            return datetime.now(timezone.utc), "unknown"
        
        print(latest_commit.committed_datetime, latest_commit.author.email)
        return latest_commit.committed_datetime, latest_commit.author.email
    except Exception:
        # Fallback for newly added files/lines not yet committed
        return datetime.now(timezone.utc), "unknown"

def enrich_block(block):
    """Generates a deep functional summary and embedding for every code unit."""
    
    system_instruction = (
        "You are a Senior Technical Architect. Summarize the provided code unit in 1 concise sentence. "
        "Focus on its functional purpose and its role within the system. "
        "Do NOT say 'This code...' or 'This function...'. Start directly with an action verb. "
        "Provide a meaningful description even for boilerplate or setup code."
    )
    
    summary = get_llm_completion(
        system_instruction, 
        f"File Path: {block.file_path}\nUnit Name: {block.name}\nContent:\n{block.content[:2000]}"
    )
    
    if not summary:
        return None
        
    return {
        "summary": summary,
        "embedding": get_embedding(block.content),
        "footprint": generate_footprint(block.content)
    }

async def ingest_repo(repo_url, project_id, user_id, progress_callback=None):
    try:
        repo_path = os.path.abspath(f"./temp_repos/{project_id}")
        
        if progress_callback: progress_callback("CLONING", f"Cloning {repo_url}...")
        
        if os.path.exists(repo_path):
            repo = git.Repo(repo_path)
            repo.remotes.origin.pull()
        else:
            os.makedirs(os.path.dirname(repo_path), exist_ok=True)
            repo = git.Repo.clone_from(repo_url, repo_path)

        latest_sha = repo.head.object.hexsha
        supabase.table("projects").update({"last_commit": latest_sha}).eq("id", project_id).execute()
        if progress_callback: progress_callback("METADATA", f"Tracking commit: {latest_sha[:7]}")
        
        parser = AdvancedCodeParser()
        current_scan_identifiers = []

        for root, _, files in os.walk(repo_path):
            if '.git' in root: continue
            
            for file in files:
                file_path = os.path.join(root, file)
                if not parser.filter_process(file_path): continue

                rel_path = os.path.relpath(file_path, repo_path)
                blocks = parser.parse_file(file_path)
                if not blocks: continue
                
                for block in blocks:
                    parent = block.parent_block if block.parent_block else 'root'
                    clean_id = f"{rel_path}::{parent}::{block.name}"
                    
                    # 1. DIFFERENTIAL SYNC CHECK
                    current_hash = generate_footprint(block.content)
                    existing_hash = get_unit_footprint(project_id, clean_id)
                    
                    if existing_hash == current_hash:
                        current_scan_identifiers.append(clean_id)
                        continue 

                    # 2. CONTENT CHANGED: Reprocess
                    if progress_callback: progress_callback("PROCESSING", f"Updating {block.name}...")
                    
                    # <-- ADDED HERE: Calculate accurate line-level git data per function
                    last_mod, author = get_function_metadata(repo_path, file_path, block.start_line, block.end_line, repo)
                    
                    enrichment = enrich_block(block)
                    
                    unit_data = {
                        "identifier": clean_id,
                        "type": block.type,
                        "file_path": rel_path,
                        "content": block.content,
                        "summary": enrichment['summary'] if enrichment else "Logic implementation for " + block.name,
                        "footprint": current_hash,
                        "embedding": enrichment['embedding'] if enrichment else None,
                        "last_modified_at": last_mod.isoformat() if last_mod else None,
                        "author_email": author
                    }
                    
                    save_memory_unit(project_id, unit_data)
                    current_scan_identifiers.append(clean_id)

                    # 3. UPDATE EDGES
                    if block.calls: save_edges(project_id, clean_id, block.calls, "calls")
                    if block.imports: save_edges(project_id, clean_id, [i.module for i in block.imports], "imports")
                    if block.bases: save_edges(project_id, clean_id, block.bases, "inherits")

        # 4. CLEANUP ORPHANS
        if progress_callback: progress_callback("CLEANUP", "Removing deleted files...")
        db_units = supabase.table("memory_units").select("unit_name").eq("project_id", project_id).execute()
        db_unit_names = {u['unit_name'] for u in db_units.data}
        
        # Identify orphans (in DB but not in current_scan_identifiers)
        orphans = list(db_unit_names - set(current_scan_identifiers))
        
        if orphans:
            print(f"🗑️ Deleting {len(orphans)} orphaned units...")
            
            # 1. Delete associated edges where the orphan is the SOURCE
            supabase.table("graph_edges").delete().eq("project_id", project_id).in_("source_unit_name", orphans).execute()
            supabase.table("memory_units").delete().eq("project_id", project_id).in_("unit_name", orphans).execute()

        # 5. RISK INTELLIGENCE TRIGGER
        if progress_callback: progress_callback("INTELLIGENCE", "Analyzing Predictive Risks...")
        
        count = await calculate_predictive_risks(project_id)
        
        if progress_callback: progress_callback("DONE", f"Sync Complete. {count} Risks Found.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        if progress_callback: progress_callback("Error", str(e))