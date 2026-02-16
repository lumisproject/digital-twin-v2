import uuid
import logging
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import your core modules
from src.agent import LumisAgent
from src.ingestor import ingest_repo
from src.retriever import GraphRetriever
from src.db_client import supabase

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LumisAPI")

# --- IN-MEMORY SESSION STORE ---
# In production, use Redis. For now, we store active agents in memory.
# Format: { "session_id": LumisAgent_instance }
active_agents: Dict[str, LumisAgent] = {}

# --- DATA MODELS (Pydantic) ---
class ChatRequest(BaseModel):
    project_id: str
    query: str
    session_id: Optional[str] = None  # Client can send a unique ID to maintain history
    mode: str = "multi-turn"          # "multi-turn" or "single-turn"

class IngestRequest(BaseModel):
    repo_url: str
    project_id: str
    user_id: Optional[str] = "api-user"

class ChatResponse(BaseModel):
    answer: str
    session_id: str

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Lumis API starting up...")
    yield
    active_agents.clear()
    logger.info("🛑 Lumis API shutting down...")

# --- APP SETUP ---
app = FastAPI(title="Lumis Digital Twin API", version="1.0", lifespan=lifespan)

# CORS (Allow your future frontend to talk to this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "running", "active_sessions": len(active_agents)}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main Chat Interface.
    Maintains conversation history if session_id is provided.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # 1. Get or Create Agent
    if session_id not in active_agents:
        logger.info(f"✨ Creating new agent for session: {session_id}")
        try:
            # Initialize the agent (this connects to Supabase)
            agent = LumisAgent(project_id=req.project_id, mode=req.mode)
            active_agents[session_id] = agent
        except Exception as e:
            logger.error(f"Failed to init agent: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    agent = active_agents[session_id]

    # 2. Ask the Agent (This runs the Adaptive Loop)
    try:
        response_text = agent.ask(req.query)
        return ChatResponse(answer=response_text, session_id=session_id)
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise HTTPException(status_code=500, detail=f"Agent reasoning failed: {str(e)}")

@app.post("/ingest")
async def ingest_endpoint(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Triggers repository ingestion in the background.
    """
    # Define a wrapper for logging
    def run_ingestion():
        logger.info(f"🔄 Starting background ingestion for {req.repo_url}...")
        try:
            # We use a simple print callback for server logs
            ingest_repo(req.repo_url, req.project_id, req.user_id, progress_callback=lambda t, m: logger.info(f"[{t}] {m}"))
            logger.info(f"✅ Ingestion complete for {req.project_id}")
        except Exception as e:
            logger.error(f"❌ Ingestion failed: {e}")

    # Add to background tasks so API responds immediately
    background_tasks.add_task(run_ingestion)
    
    return {"message": "Ingestion started", "project_id": req.project_id, "status": "processing"}

@app.get("/files/{project_id}")
def list_files_endpoint(project_id: str):
    """
    Returns the file structure for the frontend file tree.
    """
    try:
        retriever = GraphRetriever(project_id)
        files = retriever.list_all_files()
        return {"project_id": project_id, "files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    """
    Clears the memory for a specific user session.
    """
    if session_id in active_agents:
        del active_agents[session_id]
        return {"message": "Session cleared"}
    raise HTTPException(status_code=404, detail="Session not found")