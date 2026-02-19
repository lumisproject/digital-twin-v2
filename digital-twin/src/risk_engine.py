from datetime import datetime, timezone
from src.db_client import get_project_data, save_risk_alerts, update_unit_risk_scores
from src.services import get_llm_completion

def analyze_conflict_with_llm(source_name, source_summary, target_name, target_summary):
    """
    Uses the LLM to determine if the interaction between new and legacy code is dangerous.
    NOTE: Using 'summary' instead of full code prevents API cost blowouts.
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
    
    analysis = get_llm_completion(system_prompt, user_prompt)
    return analysis if analysis else "Standard dependency risk detected."


def calculate_predictive_risks(project_id):
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

    # 3. Detect Conflicts (Edges) using Relative Age Difference
    risks = []
    risk_scores = {}
    
    print(f"Analyzing {len(edges)} dependencies for conflicts...")
    
    for edge in edges:
        source_name = edge['source_unit_name']
        target_name = edge['target_unit_name']
        
        source_key = next((k for k in unit_map.keys() if k == source_name or k.endswith(f"::{source_name}")), None)
        target_key = next((k for k in unit_map.keys() if k == target_name or k.endswith(f"::{target_name}")), None)

        if source_key and target_key:
            source_unit = unit_map[source_key]
            target_unit = unit_map[target_key]
            
            # THE FIX: Calculate the relative difference in age between dependent units
            age_difference = target_unit['age_days'] - source_unit['age_days']
            
            # RULE: If active code (< 30 days) depends on code that is significantly older (> 90 days older)
            if source_unit['age_days'] < 30 and age_difference > 90:
                
                print(f"Detected conflict: {source_key} -> {target_key}")
                
                # Pass 'summary' instead of 'content' to save thousands of API tokens
                analysis = analyze_conflict_with_llm(
                    source_key, source_unit.get('summary', 'No summary available.'),
                    target_key, target_unit.get('summary', 'No summary available.')
                )
                
                description = (
                    f"Legacy Conflict: Active code '{source_key}' depends on '{target_key}' "
                    f"(untouched for {target_unit['age_days']} days).\n"
                    f"AI Analysis: {analysis}"
                )
                
                risks.append({
                    "project_id": project_id,
                    "risk_type": "Legacy Conflict",
                    "severity": "Medium" if age_difference < 180 else "High", 
                    "description": description,
                    "affected_units": [source_key, target_key]
                })
                
                # Increase Risk Scores
                risk_scores[source_key] = risk_scores.get(source_key, 0) + 25
                risk_scores[target_key] = risk_scores.get(target_key, 0) + 10

    # 4. Base Risk Scores (Age Factors)
    score_updates = []
    for u_name, unit in unit_map.items():
        current_score = risk_scores.get(u_name, 0)
        
        # Baseline risk for code older than 120 days
        if unit['age_days'] > 120:
            current_score += 10
            
        final_score = min(current_score, 100)
        
        if final_score > 0:
            score_updates.append({
                "project_id": project_id,
                "unit_name": u_name,
                "risk_score": final_score
            })

    # 5. Save Results
    print(f"Saving {len(risks)} legacy conflicts.")
    save_risk_alerts(project_id, risks)
    update_unit_risk_scores(score_updates)
    
    return len(risks)