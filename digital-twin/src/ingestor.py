import os
import git
import time
from tree_sitter_language_pack import get_parser
from src.services import get_llm_completion, get_embedding, generate_footprint
from src.db_client import supabase, save_memory_unit, save_edges, get_unit_footprint
from src.indexing.parser import AdvancedCodeParser
from src.risk_engine import calculate_predictive_risks

def get_git_metadata(repo_path, file_path, repo_obj):
    try:
        rel_path = os.path.relpath(file_path, repo_path)
        # Get the last commit that actually touched this file
        commits = list(repo_obj.iter_commits(paths=rel_path, max_count=1))
        if not commits: return None, None
        return commits[0].committed_datetime, commits[0].author.email
    except:
        return None, None

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

def ingest_repo(repo_url, project_id, user_id, progress_callback=None):
    try:
        repo_path = os.path.abspath(f"./temp_repos/{project_id}")
        
        if progress_callback: progress_callback("CLONING", f"Cloning {repo_url}...")
        
        if os.path.exists(repo_path):
            repo = git.Repo(repo_path)
            repo.remotes.origin.pull()
        else:
            os.makedirs(os.path.dirname(repo_path), exist_ok=True)
            repo = git.Repo.clone_from(repo_url, repo_path)

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
                
                last_mod, author = get_git_metadata(repo_path, file_path, repo)

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
        
        count = calculate_predictive_risks(project_id)
        
        if progress_callback: progress_callback("DONE", f"Sync Complete. {count} Risks Found.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        if progress_callback: progress_callback("Error", str(e))