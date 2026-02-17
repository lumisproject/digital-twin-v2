from datetime import datetime, timezone
from src.db_client import get_project_data, save_risk_alerts, update_unit_risk_scores
from src.services import get_llm_completion

def analyze_conflict_with_llm(source_name, source_code, target_name, target_code):
    """
    Uses the LLM to determine if the interaction between new and legacy code is dangerous.
    """
    system_prompt = (
        "You are the Lumis Senior Software Architect. Your tone is cynical, investigative, and direct. "
        "You are analyzing a 'Legacy Conflict': a recently modified function depending on a legacy function unchanged for months.\n\n"
        "STRICT ANALYSIS RULES:\n"
        "1. DATA CONTRACTS: Check if the recent code assumes new data types, nullability, or object structures that the legacy code doesn't handle.\n"
        "2. SIDE EFFECTS: Does the legacy function have hidden side effects (global state, disk I/O) that the new caller might not expect?\n"
        "3. PERFORMANCE: Will the new caller trigger the legacy code more frequently than originally designed, causing a bottleneck?\n"
        "4. NO FLUFF: Do not say 'It is important to note'. Get straight to the technical risk."
    )
    
    user_prompt = (
        f"--- RECENT CALLER ({source_name}) ---\n"
        f"{source_code}\n\n"
        f"--- LEGACY DEPENDENCY ({target_name}) ---\n"
        f"{target_code}\n\n"
        "TASK: Explain the specific technical danger of this dependency in 1-2 high-density sentences. "
        "If you see no specific conflict, state: 'Standard dependency risk; monitor for regression.'"
    )
    
    analysis = get_llm_completion(system_prompt, user_prompt)
    return analysis if analysis else "Architectural analysis unavailable; manual review required."

def calculate_predictive_risks(project_id):
    """Fetches graph data and applies age-based thresholds to detect conflicts."""
    # 1. Fetch unified data using your db_client
    units, edges = get_project_data(project_id)
    if not units:
        return 0

    now = datetime.now(timezone.utc)
    LEGACY_THRESHOLD = 90  # 3 months
    RECENT_THRESHOLD = 30   # 1 month
    
    legacy_units = {}
    recent_units = set()
    unit_map = {u['unit_name']: u for u in units}
    
    # 2. Categorize units by age using metadata from ingestor
    for unit in units:
        if not unit.get('last_modified_at'):
            continue
        last_mod = datetime.fromisoformat(unit['last_modified_at'].replace('Z', '+00:00'))
        age_days = (now - last_mod).days
        
        if age_days > LEGACY_THRESHOLD:
            legacy_units[unit['unit_name']] = unit
        elif age_days < RECENT_THRESHOLD:
            recent_units.add(unit['unit_name'])

    risks = []
    score_updates = []
    
    # 3. Analyze edges for Legacy Conflicts
    for edge in edges:
        src, target = edge['source_unit_name'], edge['target_unit_name']
        if src in recent_units and target in legacy_units:
            analysis = analyze_conflict_with_llm(src, unit_map[src]['content'], target, legacy_units[target]['content'])
            
            risks.append({
                "project_id": project_id,
                "risk_type": "Legacy Conflict",
                "severity": "Medium",
                "description": f"Active code '{src}' calls legacy '{target}'. AI: {analysis}",
                "affected_units": [src, target]
            })
            
            # Prepare risk score bumps for memory_units
            score_updates.append({"project_id": project_id, "unit_name": src, "risk_score": 25.0})

    # 4. Save results via your db_client
    save_risk_alerts(project_id, risks)
    update_unit_risk_scores(score_updates)
    
    return len(risks)