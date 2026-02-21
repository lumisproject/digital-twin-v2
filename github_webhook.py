from fastapi import APIRouter, Request, HTTPException
import re
import requests
from jira.client import get_issue, get_accessible_resources, get_issue_details
from jira.actions import add_comment, transition_issue, create_issue
from logic.ai_engine import analyze_fulfillment
from token_store import get_valid_token
from config import GITHUB_TOKEN

github_router = APIRouter()

TASK_ID_REGEX = r"\b([A-Z]{2,10})-(\d+)\b"

def extract_tasks(message: str):
    match = re.search(TASK_ID_REGEX, message)
    if not match: return None
    full_id = match.group(0)
    prefix = match.group(1)
    platform = "jira" if prefix != "LIN" else "linear"
    return {"id": full_id, "platform": platform}

@github_router.post("/webhook/github")
async def github_webhook(request: Request):
    payload = await request.json()
    commits = payload.get("commits", [])
    
    user_id = "demo-user" 
    access_token = get_valid_token(user_id)
    if not access_token:
        raise HTTPException(status_code=401, detail="Jira not connected")

    resources = get_accessible_resources(access_token)
    if not resources:
        return {"status": "no sites found"}
    cloud_id = resources[0]["id"]

    results = []
    for commit in commits:
        task = extract_tasks(commit["message"])
        if not task or task["platform"] != "jira":
            continue

        try:
            # 1. Fetch the actual code changes (Diff) from GitHub
            # Adding .diff to a commit URL provides the raw text diff
            diff_url = commit.get("url") + ".diff"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            diff_res = requests.get(diff_url, headers=headers)
            code_diff = diff_res.text if diff_res.status_code == 200 else "No diff available"

            # 2. Get the Jira Task requirements
            issue_details = get_issue_details(cloud_id, task["id"], access_token)

            # 3. AI Analysis: Compare Diff vs Jira Task
            analysis = analyze_fulfillment(issue_details, code_diff)
            
            # 4. Take Action based on AI report
            add_comment(cloud_id, task["id"], f"🤖 **AI Analysis Report:**\n\n{analysis['summary']}", access_token)
            
            # If AI says the task is complete, move it to Done
            if analysis["status"] == "COMPLETE":
                transition_issue(cloud_id, task["id"], "Done", access_token)
            
            # If AI identifies new sub-tasks or technical debt, create them
            for new_task in analysis.get("new_tasks", []):
                project_key = task["id"].split("-")[0]
                create_issue(
                    cloud_id, 
                    project_key, 
                    f"Follow-up: {new_task['title']}", 
                    f"Identified from commit for {task['id']}: {new_task['description']}", 
                    access_token
                )

            results.append({"task": task["id"], "status": analysis["status"]})
                        
        except Exception as e:
            print(f"Error processing {task.get('id')}: {e}")

    return {"status": "processed", "updates": results}