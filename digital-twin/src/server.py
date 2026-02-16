import logging
import asyncio # Added for non-blocking execution
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
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
    state["step"] = task
    if message:
        state["logs"].append(f"[{task}] {message}")
    
    # "DONE" task explicitly triggers the frontend redirection
    if task == "DONE":
        state["status"] = "completed"
    elif task == "Error":
        state["status"] = "failed"
        state["error"] = message

# --- ENDPOINTS ---

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
        existing = supabase.table("projects").select("id, last_commit").eq("repo_url", req.repo_url).execute()
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)