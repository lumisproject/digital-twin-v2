import os
import git
import asyncio
from datetime import datetime, timezone
from src.services import embed_model, generate_footprint
from src.db_client import supabase, save_memory_units, save_edges, get_unit_footprint
from src.indexing.parser import AdvancedCodeParser
from src.risk_engine import calculate_predictive_risks

# --- FASTCODE OPTIMIZATION: BATCH GIT BLAME ---
def get_file_blame_metadata(repo_path, file_path, repo_obj):
    """Runs git blame ONCE per file and maps each line to its last author and commit time."""
    rel_path = os.path.relpath(file_path, repo_path)
    line_metadata = {}
    
    try:
        blame = repo_obj.blame('HEAD', rel_path)
        current_line = 1
        
        for commit, lines in blame:
            dt = commit.committed_datetime
            email = commit.author.email
            for _ in lines:
                line_metadata[current_line] = (dt, email)
                current_line += 1
                
        return line_metadata
    except Exception as e:
        print(f"Blame failed for {rel_path}: {e}")
        return {}


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
        
        # In-memory batch queues
        blocks_to_embed = []
        edges_to_insert = []

        for root, _, files in os.walk(repo_path):
            if '.git' in root: continue
            
            for file in files:
                file_path = os.path.join(root, file)
                if not parser.filter_process(file_path): continue

                rel_path = os.path.relpath(file_path, repo_path)
                blocks = parser.parse_file(file_path)
                if not blocks: continue
                
                # Fetch blame metadata ONCE for the entire file
                file_blame_meta = get_file_blame_metadata(repo_path, file_path, repo)
                
                for block in blocks:
                    parent = block.parent_block if block.parent_block else 'root'
                    clean_id = f"{rel_path}::{parent}::{block.name}"
                    
                    # 1. DIFFERENTIAL SYNC CHECK
                    current_hash = generate_footprint(block.content)
                    existing_hash = get_unit_footprint(project_id, clean_id)
                    
                    if existing_hash == current_hash:
                        current_scan_identifiers.append(clean_id)
                        continue 

                    # 2. FAST IN-MEMORY PROCESSING (Hold data instead of embedding immediately)
                    if progress_callback: progress_callback("PROCESSING", f"Parsing {block.name}...")
                    
                    s_line = max(1, block.start_line + 1)
                    last_mod, author = file_blame_meta.get(s_line, (datetime.now(timezone.utc), "unknown"))
                    
                    blocks_to_embed.append({
                        "identifier": clean_id,
                        "type": block.type,
                        "file_path": rel_path,
                        "content": block.content,
                        "name": block.name,
                        "footprint": current_hash,
                        "last_mod": last_mod.isoformat() if last_mod else None,
                        "author": author
                    })
                    current_scan_identifiers.append(clean_id)

                    # 3. COLLECT EDGES FOR BULK INSERT
                    if block.calls: 
                        edges_to_insert.extend([{"project_id": project_id, "source_unit_name": clean_id, "target_unit_name": t, "edge_type": "calls"} for t in block.calls])
                    if block.imports: 
                        edges_to_insert.extend([{"project_id": project_id, "source_unit_name": clean_id, "target_unit_name": i.module, "edge_type": "imports"} for i in block.imports])
                    if block.bases: 
                        edges_to_insert.extend([{"project_id": project_id, "source_unit_name": clean_id, "target_unit_name": b, "edge_type": "inherits"} for b in block.bases])

        # --- NEW: DEDUPLICATE TO PREVENT POSTGRES BULK ERRORS ---
        # 1. Deduplicate memory units by their unique identifier
        unique_blocks = {}
        for b in blocks_to_embed:
            unique_blocks[b["identifier"]] = b
        blocks_to_embed = list(unique_blocks.values())

        # 2. Deduplicate graph edges to prevent duplicate relations
        unique_edges_set = set()
        deduped_edges = []
        for e in edges_to_insert:
            e_tuple = (e["source_unit_name"], e["target_unit_name"], e["edge_type"])
            if e_tuple not in unique_edges_set:
                unique_edges_set.add(e_tuple)
                deduped_edges.append(e)
        edges_to_insert = deduped_edges
        # --------------------------------------------------------

        # --- FASTCODE OPTIMIZATION: BATCH EMBEDDING ---
        if progress_callback: progress_callback("EMBEDDING", "Generating Vector Embeddings in Bulk...")
        
        units_to_insert = []
        if blocks_to_embed:
            # Extract all contents into a single list
            all_contents = [b["content"] for b in blocks_to_embed]
            
            # Fire ONE call to embed everything at once directly via the model
            bulk_embeddings = embed_model.encode(all_contents, batch_size=32).tolist()
            
            # Re-associate embeddings with their metadata
            for i, b in enumerate(blocks_to_embed):
                units_to_insert.append({
                    "identifier": b["identifier"],
                    "type": b["type"],
                    "file_path": b["file_path"],
                    "content": b["content"],
                    "summary": f"Functional extraction for {b['name']}",
                    "footprint": b["footprint"],
                    "embedding": bulk_embeddings[i], # Attach batched embedding
                    "last_modified_at": b["last_mod"],
                    "author_email": b["author"]
                })


        # --- FASTCODE OPTIMIZATION: BULK NETWORK EXECUTION ---
        if progress_callback: progress_callback("DATABASE", "Bulk inserting vectors to Supabase...")
        
        # Batch insert chunks of 100 to avoid payload size errors
        batch_size = 100
        for i in range(0, len(units_to_insert), batch_size):
            save_memory_units(project_id, units_to_insert[i:i + batch_size])
            
        for i in range(0, len(edges_to_insert), batch_size):
            save_edges(project_id, edges_to_insert[i:i + batch_size])


        # 4. CLEANUP ORPHANS
        if progress_callback: progress_callback("CLEANUP", "Removing deleted files...")
        db_units = supabase.table("memory_units").select("unit_name").eq("project_id", project_id).execute()
        db_unit_names = {u['unit_name'] for u in db_units.data}
        
        orphans = list(db_unit_names - set(current_scan_identifiers))
        
        if orphans:
            print(f"🗑️ Deleting {len(orphans)} orphaned units...")
            supabase.table("graph_edges").delete().eq("project_id", project_id).in_("source_unit_name", orphans).execute()
            supabase.table("memory_units").delete().eq("project_id", project_id).in_("unit_name", orphans).execute()


        # 5. FASTCODE OPTIMIZATION: DECOUPLED RISK ENGINE
        if progress_callback: progress_callback("DONE", "Fast Sync Complete. Running Intelligence in Background...")
        
        # Push the heavy predictive logic to the background so the user gets an instant 'Success' response
        asyncio.create_task(calculate_predictive_risks(project_id))

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        if progress_callback: progress_callback("Error", str(e))