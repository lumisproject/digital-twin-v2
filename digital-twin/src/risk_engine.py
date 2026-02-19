import asyncio
from datetime import datetime, timezone
import networkx as nx
from src.db_client import get_project_data, save_risk_alerts, update_unit_risk_scores
from src.services import get_llm_completion

async def analyze_conflict_with_llm(source_name, source_summary, target_name, target_summary):
    """
    Uses the LLM to determine if the interaction between new and legacy code is dangerous.
    Runs asynchronously to prevent blocking.
    """
    system_prompt = (
        "You are a Senior Software Architect specializing in legacy modernization. "
        "Analyze the interaction between a RECENTLY MODIFIED function and a LEGACY function (unchanged for months). "
        "Predict if the recent changes might break assumptions in the legacy code based on their summaries. "
        "Be concise. Focus on data flow, responsibilities, and architecture assumptions."
    )
    
    user_prompt = (
        f"--- RECENT CODE ({source_name}) ---\n"
        f"Summary: {source_summary}\n\n"
        f"--- LEGACY CODE ({target_name}) ---\n"
        f"Summary: {target_summary}\n\n"
        "TASK: Explain the potential risk in 1-2 sentences. If the risk is generic, say 'Standard dependency risk'."
    )
    
    # Wrap synchronous LLM call to run in a separate thread to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    analysis = await loop.run_in_executor(None, get_llm_completion, system_prompt, user_prompt)
    return analysis if analysis else "Standard dependency risk detected."


async def calculate_predictive_risks(project_id):
    print(f"Starting Risk Analysis for {project_id}...")
    
    # 1. Fetch Graph Data
    units, edges = get_project_data(project_id)
    if not units:
        return 0

    now = datetime.now(timezone.utc)
    unit_map = {}
    
    # 2. Map all units and calculate exact age in days
    for unit in units:
        if not unit.get('last_modified_at'): continue
            
        try:
            last_mod = datetime.fromisoformat(unit['last_modified_at'].replace('Z', '+00:00'))
            unit['age_days'] = (now - last_mod).days
            unit_map[unit['unit_name']] = unit
        except ValueError:
            continue 

    # 3. BUILD THE SMART GRAPH
    # This resolves Symbol Ambiguity by checking imports before linking functions
    G = nx.DiGraph()
    
    # Map imports per file for fast lookup: { "full_file_path": ["imported.module.path"] }
    import_map = {}
    for edge in edges:
        if edge.get('edge_type') == 'imports' or '::' not in edge['target_unit_name']:
            src_file = edge['source_unit_name'].split('::')[0]
            if src_file not in import_map: import_map[src_file] = []
            import_map[src_file].append(edge['target_unit_name'])

    for edge in edges:
        # Only process function calls for the graph nodes
        source_id = edge['source_unit_name']
        target_short_name = edge['target_unit_name']
        
        if source_id not in unit_map: continue

        # Find all potential fully-qualified units that match this short name
        potential_targets = [k for k in unit_map.keys() if k.endswith(f"::{target_short_name}")]
        
        for target_id in potential_targets:
            src_file = source_id.split('::')[0]
            tgt_file = target_id.split('::')[0]
            
            # Normalize target module path for comparison (e.g. database\provider.py -> database.provider)
            target_mod_path = tgt_file.replace('\\', '.').replace('/', '.').replace('.py', '')
            
            # RULE: Link them if they are in the same file OR if the source file imports the target's module
            file_imports = import_map.get(src_file, [])
            if src_file == tgt_file or any(imp in target_mod_path for imp in file_imports):
                G.add_edge(source_id, target_id)

    # 4. Detect Conflicts using Multi-hop Pathfinding (Indirect Dependencies)
    risks = []
    risk_scores = {}
    llm_coroutines = []
    conflict_details = []
    
    active_units = [k for k, v in unit_map.items() if v['age_days'] < 30]
    legacy_units = [k for k, v in unit_map.items() if v['age_days'] > 80] # Using 80 for safer test margin 

    print(f"Analyzing paths from {len(active_units)} active units to {len(legacy_units)} older units...")

    for source in active_units:
        if source not in G: continue
        for target in legacy_units:
            if target not in G or source == target: continue
            
            # nx.has_path checks for indirect dependencies (Depth 1, 2, or 3)
            if nx.has_path(G, source, target):
                path = nx.shortest_path(G, source, target)
                if 1 < len(path) <= 4: # Limit to 3 hops (4 nodes in path)
                    
                    source_unit = unit_map[source]
                    target_unit = unit_map[target]
                    age_difference = target_unit['age_days'] - source_unit['age_days']
                    
                    # TRIGGER: Significant relative age gap detected along a dependency path
                    if age_difference > 80:
                        print(f"Detected conflict: {source} -> {target} (Path length: {len(path)-1})")
                        
                        coro = analyze_conflict_with_llm(
                            source, source_unit.get('summary', 'No summary available.'),
                            target, target_unit.get('summary', 'No summary available.')
                        )
                        llm_coroutines.append(coro)
                        
                        conflict_details.append({
                            "source_key": source,
                            "target_key": target,
                            "target_age": target_unit['age_days'],
                            "age_difference": age_difference,
                            "path": " -> ".join(path)
                        })
                        
                        risk_scores[source] = risk_scores.get(source, 0) + 25
                        risk_scores[target] = risk_scores.get(target, 0) + 10

    # 5. Run LLM analyses concurrently
    if llm_coroutines:
        print(f"Running {len(llm_coroutines)} parallel AI risk assessments...")
        analyses = await asyncio.gather(*llm_coroutines)
        
        for i, analysis_result in enumerate(analyses):
            det = conflict_details[i]
            description = (
                f"Legacy Conflict detected via path: {det['path']}\n"
                f"Active code depends on a unit untouched for {det['target_age']} days.\n"
                f"AI Analysis: {analysis_result}"
            )
            risks.append({
                "project_id": project_id,
                "risk_type": "Legacy Conflict",
                "severity": "High" if det['age_difference'] > 150 else "Medium", 
                "description": description,
                "affected_units": [det['source_key'], det['target_key']]
            })

    # 6. Update Database Risk Scores
    score_updates = []
    for u_name, unit in unit_map.items():
        current_score = risk_scores.get(u_name, 0)
        if unit['age_days'] > 120: current_score += 10
        final_score = min(current_score, 100)
        
        if final_score > 0:
            score_updates.append({
                "project_id": project_id, "unit_name": u_name, "risk_score": final_score
            })

    # 7. Save Results (Consider using an upsert helper if available)
    print(f"Saving {len(risks)} legacy conflicts.")
    save_risk_alerts(project_id, risks)
    update_unit_risk_scores(score_updates)
    
    return len(risks)