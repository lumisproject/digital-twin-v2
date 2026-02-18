import logging
import asyncio # Added for non-blocking execution
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Core Modules
from src.agent import LumisAgent
from src.ingestor import ingest_repo
from src.db_client import supabase, get_project_risks

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LumisAPI")

app = FastAPI(title="Lumis Digital Twin API")

# Allow Frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- STATE MANAGEMENT ---
active_agents: Dict[str, LumisAgent] = {}
ingestion_state: Dict[str, Dict] = {}

# --- MODELS ---
class ChatRequest(BaseModel):
    project_id: str
    query: str
    mode: str = "multi-turn"
    reasoning: bool = False # Added field for toggle

class IngestRequest(BaseModel):
    user_id: str
    repo_url: str

# --- HELPER: Ingestion Progress Tracker ---
def update_progress(project_id, task, message):
    if project_id not in ingestion_state:
        ingestion_state[project_id] = {"status": "processing", "logs": [], "step": "Starting"}
    
    state = ingestion_state[project_id]

    if task == "STARTING":
        state["status"]="PROGRESSING"
        state["logs"]=[]
        state["error"]=None
    
    state["step"]=task

    if message:
        state["logs"].append(f"[{task}] {message}")

    if task == "DONE":
        state["status"] = "completed"
    elif task == "Error":
        state["status"] = "failed"
        state["error"] = message
    elif task != "STARTING": 
        state["status"] = "PROCESSING"

# --- ENDPOINTS ---

@app.post("/api/webhook/{user_id}/{project_id}")
async def github_webhook(user_id: str, project_id: str, request: Request, background_tasks: BackgroundTasks):
    try:
        # 1. Fetch project safely
        res = supabase.table("projects") \
            .select("*") \
            .eq("id", project_id) \
            .eq("user_id", user_id) \
            .maybe_single() \
            .execute()

        # Handle missing project (common if DB was truncated)
        if not res or not res.data:
            logger.warning(f"Webhook Ignored: Project {project_id} not found for user {user_id}")
            return {"status": "ignored", "reason": "project_not_found"}

        payload = await request.json()

        # 2. Handle GitHub's "Zen" test ping
        if "zen" in payload:
            logger.info("GitHub Zen ping received. Connection verified.")
            return {"status": "ok", "message": "Lumis is listening"}

        # 3. Handle Push Events
        ref = payload.get("ref", "")
        if "refs/heads/" in ref:
            new_sha = payload.get("after")
            repo_url = payload.get("repository", {}).get("clone_url")
            supabase.table("projects").update({"last_commit": new_sha}).eq("id", project_id).execute()
            logger.info(f"Webhook Trigger: Push detected on {ref} (Commit: {new_sha[:7]})")

            update_progress(
                project_id, 
                "STARTING", 
                f"GitHub Push detected ({new_sha[:7]}). Initializing Twin Sync..."
            )

            # 4. Fire and forget: Run the full ingestion in the background
            background_tasks.add_task(
                ingest_repo,
                repo_url=repo_url,
                project_id=project_id,
                user_id=user_id,
                progress_callback=lambda t, m: update_progress(project_id, t, m)
            )

            return {"status": "sync_started", "commit": new_sha}

        return {"status": "ignored", "reason": "not_a_push_event"}

    except Exception as e:
        logger.error(f"CRITICAL: Webhook Processing Error: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Handles chat requests. Uses asyncio.to_thread to prevent blocking the event loop.
    """
    try:
        # 1. Initialize or Update Agent
        if req.project_id not in active_agents:
            logger.info(f"✨ Spawning agent for {req.project_id}")
            active_agents[req.project_id] = LumisAgent(project_id=req.project_id, mode=req.mode)
        
        agent = active_agents[req.project_id]
        agent.mode = req.mode
        
        # 2. Execute agent logic in a background thread to keep the API responsive
        response_text = await asyncio.to_thread(
            agent.ask, 
            req.query, 
            reasoning_enabled=req.reasoning
        )
        
        return {"response": response_text}
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest")
async def start_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    try:
        existing = supabase.table("projects").select("id, last_commit").eq("repo_url", req.repo_url).eq("user_id", req.user_id).execute()
        if existing.data:
            project_id = existing.data[0]['id']
        else:
            res = supabase.table("projects").insert({
                "user_id": req.user_id, "repo_url": req.repo_url
            }).execute()
            project_id = res.data[0]['id']

        ingestion_state[project_id] = {"status": "starting", "logs": ["Request received..."], "step": "Init"}

        background_tasks.add_task(
            ingest_repo,
            repo_url=req.repo_url,
            project_id=project_id,
            user_id=req.user_id,
            progress_callback=lambda t, m: update_progress(project_id, t, m)
        )
        
        return {"project_id": project_id, "status": "started"}
    except Exception as e:
        logger.error(f"Ingest start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ingest/status/{project_id}")
async def get_ingest_status(project_id: str):
    return ingestion_state.get(project_id, {"status": "idle", "logs": [], "step": "Ready"})

@app.get("/api/risks/{project_id}")
async def get_risks_endpoint(project_id: str):
    risks = get_project_risks(project_id)
    return {"status": "success", "risks": risks if risks else []}

@app.get("/api/status")
async def health_check():
    """Simple health check for the frontend."""
    return {"status": "ok", "service": "Lumis Digital Twin"}

if __name__ == "__main__":
    import uvicorn
    # Use the port defined by your environment or default to 5000
    uvicorn.run(app, host='0.0.0.0', port=5000)