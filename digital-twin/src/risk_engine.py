from datetime import datetime, timezone, timedelta
from src.db_client import get_project_data, save_risk_alerts, update_unit_risk_scores
from src.services import get_llm_completion

def analyze_conflict(source, target, source_code, target_code):
    prompt = (
        f"Analyze this software dependency risk.\n"
        f"New Code ({source}) calls Legacy Code ({target}).\n"
        f"Legacy Code Content:\n{target_code[:1000]}\n"
        f"New Code Content:\n{source_code[:1000]}\n"
        f"Identify 1 specific risk (data type mismatch, unhandled null, performance). Be cynical."
    )
    return get_llm_completion("You are a Senior Architect. Output 1 sentence only.", prompt)

def calculate_predictive_risks(project_id):
    # 1. Get Data
    units, edges = get_project_data(project_id)
    if not units: return 0
    
    # 2. Define Timeframes
    now = datetime.now(timezone.utc)
    # FOR TESTING: We set legacy to 60 days, recent to 1 day. 
    # Adjust these in production (e.g. 120 days).
    LEGACY_CUTOFF = now - timedelta(days=60)
    RECENT_CUTOFF = now - timedelta(days=1)
    
    legacy_units = {}
    recent_units = set()
    unit_map = {u['unit_name']: u for u in units}

    # 3. Classify Units by Age
    for u in units:
        if not u.get('last_modified_at'): continue
        # Handle ISO strings
        try:
            mod_time = datetime.fromisoformat(u['last_modified_at'].replace('Z', '+00:00'))
        except:
            continue

        if mod_time < LEGACY_CUTOFF:
            legacy_units[u['unit_name']] = u
        elif mod_time > RECENT_CUTOFF:
            recent_units.add(u['unit_name'])

    print(f"[RiskEngine] Found {len(legacy_units)} legacy units and {len(recent_units)} recent units.")

    # 4. Find Conflicts in Graph
    risks = []
    score_updates = []

    for edge in edges:
        src = edge['source_unit_name']
        tgt = edge['target_unit_name']
        
        # Check if Recent Source -> Legacy Target
        if src in recent_units and tgt in legacy_units:
            print(f"[RiskEngine] Conflict Found: {src} -> {tgt}")
            
            analysis = analyze_conflict(
                src, tgt, 
                unit_map[src].get('content', ''), 
                legacy_units[tgt].get('content', '')
            )
            
            risks.append({
                "project_id": project_id,
                "risk_type": "Legacy Conflict",
                "severity": "Medium",
                "description": f"**Dependency Risk**: {src} (New) calls {tgt} (Old).\n\n**Architect Analysis**: {analysis}"
            })
            
            score_updates.append({
                "project_id": project_id, 
                "unit_name": src, 
                "risk_score": 30.0 # High risk bump
            })

    # 5. Save
    save_risk_alerts(project_id, risks)
    update_unit_risk_scores(score_updates)
    
    return len(risks)