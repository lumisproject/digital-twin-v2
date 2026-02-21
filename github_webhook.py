from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
import re
import requests
import logging
from jira.client import get_issue, get_accessible_resources, get_issue_details
from jira.actions import add_comment, transition_issue, create_issue
from logic.ai_engine import analyze_fulfillment
from token_store import get_valid_token
from config import GITHUB_TOKEN

# Configure logging to see what's happening in the background
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

github_router = APIRouter()

# Supports JIRA (PROJ-123)
TASK_ID_REGEX = r"\b([A-Z]{2,10})-(\d+)\b"

def extract_tasks(message: str):
    """Identifies task IDs and determines the platform."""
    match = re.search(TASK_ID_REGEX, message)
    if not match: return None
    
    full_id = match.group(0)
    prefix = match.group(1)
    # Extensible for future platforms
    platform = "jira" if prefix != "LIN" else "linear"
    
    return {"id": full_id, "platform": platform}

async def process_webhook_logic(commits: list, access_token: str, cloud_id: str):
    """
    Background worker that handles the heavy lifting: 
    Diff fetching, AI analysis, and Jira updates.
    """
    for commit in commits:
        message = commit.get("message", "")
        task = extract_tasks(message)
        
        if not task or task["platform"] != "jira":
            continue

        task_id = task["id"]
        logger.info(f"Processing task {task_id} from commit: {message}")

        try:
            # 1. Fetch the actual code changes (Diff) from GitHub
            # Using the .diff extension on the commit URL is the simplest method
            diff_url = commit.get("url") + ".diff"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            diff_res = requests.get(diff_url, headers=headers, timeout=10)
            code_diff = diff_res.text if diff_res.status_code == 200 else "No diff available"

            # 2. Get the Jira Task requirements (Summary & Description)
            issue_details = get_issue_details(cloud_id, task_id, access_token)

            # 3. AI Analysis: Compare Code vs Requirements
            # Ensure your logic/ai_engine.py uses the updated dynamic version
            analysis = analyze_fulfillment(issue_details, code_diff)
            
            # 4. Update Jira with the AI Report
            report_msg = f"🤖 **AI Analysis Report:**\n\n{analysis.get('summary', 'No summary provided.')}"
            add_comment(cloud_id, task_id, report_msg, access_token)
            
            # 5. Auto-Transition if complete
            if analysis.get("status") == "COMPLETE":
                logger.info(f"Task {task_id} marked as COMPLETE. Transitioning...")
                transition_issue(cloud_id, task_id, "Done", access_token)
            
            # 6. Auto-Create Follow-up Tasks (Technical Debt / Bugs)
            for new_task in analysis.get("new_tasks", []):
                project_key = task_id.split("-")[0]
                create_issue(
                    cloud_id, 
                    project_key, 
                    f"Follow-up: {new_task['title']}", 
                    f"Auto-generated from commit {commit.get('id', '')[:7]}: {new_task['description']}", 
                    access_token
                )
                        
        except Exception as e:
            logger.error(f"Error processing {task_id}: {str(e)}")

@github_router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives the webhook, validates the token, and offloads 
    processing to a background worker to avoid timeouts.
    """
    payload = await request.json()
    commits = payload.get("commits", [])
    
    # Check for authentication before queuing
    user_id = "demo-user" 
    access_token = get_valid_token(user_id)
    if not access_token:
        # Note: If this fails, visit /auth/jira/connect to refresh memory
        raise HTTPException(status_code=401, detail="Jira session expired or not connected")

    # Get the Cloud ID
    resources = get_accessible_resources(access_token)
    if not resources:
        return {"status": "error", "message": "No Jira sites linked to this account"}
    cloud_id = resources[0]["id"]

    # Queue the heavy AI logic to run in the background
    background_tasks.add_task(process_webhook_logic, commits, access_token, cloud_id)

    return {"status": "accepted", "message": f"Processing {len(commits)} commits in background"}