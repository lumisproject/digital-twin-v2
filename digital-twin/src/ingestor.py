import os
import git
from src.services import get_llm_completion, get_embedding, generate_footprint
from src.db_client import supabase, save_memory_unit, save_edges
from src.indexing.parser import AdvancedCodeParser
from src.risk_engine import calculate_predictive_risks

def get_git_metadata(repo_path, file_path, repo_obj=None):
    try:
        repo = repo_obj if repo_obj else git.Repo(repo_path)
        rel_path = os.path.relpath(file_path, repo_path)
        commits = list(repo.iter_commits(paths=rel_path, max_count=1))
        if not commits: return None, None
        commit = commits[0]
        return commit.committed_datetime, commit.author.email
    except Exception as e:
        print(f"Warning: Git metadata failed for {file_path}: {e}")
        return None, None

def enrich_block(block):
    """Generates summary and embedding for a CodeBlock."""
    system_msg = """You are a technical analyst. 
    If the content is CODE: Summarize the core logic in one clear sentence focusing on WHAT it does and its algorithmic complexity.
    If the content is DOCUMENTATION (like a README): Summarize the project's purpose, main features, or setup instructions in one clear sentence.
    If the content is pure boilerplate or empty, return: SKIP"""
    
    context = f"File: {block.file_path}\nName: {block.name}\nType: {block.type}\nContent:\n{block.content}"
    summary = get_llm_completion(system_msg, context)
    
    if not summary or "SKIP" in summary.upper():
        return None
    
    return {
        "summary": summary,
        "embedding": get_embedding(block.content),
        "footprint": generate_footprint(block.content)
    }

def ingest_repo(repo_url, project_id, user_id, progress_callback=None):
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

    supabase.table("graph_edges").delete().eq("project_id", project_id).execute()

    for root, _, files in os.walk(repo_path):
        if '.git' in root: continue
        
        for file in files:
            file_path = os.path.abspath(os.path.join(root, file))
            # Ensure your parser.filter_process no longer blocks .md files
            if not parser.filter_process(file_path): continue

            rel_path = os.path.relpath(file_path, repo_path)
            blocks = parser.parse_file(file_path)
            if not blocks: continue
            
            last_mod, author = get_git_metadata(repo_path, file_path, repo)

            for block in blocks:
                # Proposed Logic Update for Identifiers:
                # We use 'root' if parent_block is None (common for READMEs or global variables)
                parent = block.parent_block if block.parent_block else 'root'
                clean_id = f"{rel_path}::{parent}::{block.name}"
                
                if progress_callback: progress_callback("PROCESSING", f"Analyzing {clean_id}")

                enrichment = enrich_block(block)
                
                unit_data = {
                    "identifier": clean_id, 
                    "type": block.type,
                    "file_path": rel_path,
                    "content": block.content,
                    "summary": enrichment['summary'] if enrichment else "No summary available",
                    "footprint": enrichment['footprint'] if enrichment else generate_footprint(block.content),
                    "embedding": enrichment['embedding'] if enrichment else None,
                    "last_modified_at": last_mod.isoformat() if last_mod else None,
                    "author_email": author
                }

                save_memory_unit(project_id, unit_data)
                current_scan_identifiers.append(clean_id)

                # Edge saving remains the same; it will naturally skip empty lists for READMEs
                if block.calls:
                    save_edges(project_id, clean_id, block.calls, edge_type="calls")
                if block.imports:
                    import_names = [imp.module for imp in block.imports]
                    save_edges(project_id, clean_id, import_names, edge_type="imports")
                if block.bases:
                    save_edges(project_id, clean_id, block.bases, edge_type="inherits")

    # 4. CLEANUP orphaned units
    if progress_callback: progress_callback("CLEANUP", "Removing orphan blocks...")
    db_units = supabase.table("memory_units").select("unit_name").eq("project_id", project_id).execute()
    
    if db_units.data:
        db_ids = set([u['unit_name'] for u in db_units.data])
        scan_ids = set(current_scan_identifiers)
        deleted_ids = db_ids - scan_ids

        for dead_id in deleted_ids:
            supabase.table("memory_units").delete().eq("project_id", project_id).eq("unit_name", dead_id).execute()

    latest_commit_id = repo.head.commit.hexsha
    supabase.table("projects").update({"last_commit": latest_commit_id}).eq("id", project_id).execute()

    if progress_callback: 
        progress_callback("INTELLIGENCE", "Calculating predictive risks using Graph Analysis...")

    try:
        risk_count = calculate_predictive_risks(project_id)
        if progress_callback: 
            progress_callback("DONE", f"Ingestion complete. {risk_count} risks identified.")
    except Exception as e:
        print(f"Risk analysis failed: {e}")
        if progress_callback: 
            progress_callback("DONE", "Ingestion complete (Risk analysis failed).")