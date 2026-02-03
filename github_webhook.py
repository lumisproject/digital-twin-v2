from fastapi import APIRouter, Request
from commit_parser import analyze_commit

github_router = APIRouter()

@github_router.post("/webhook")
async def github_webhook(request: Request):
    payload = await request.json()

    commits = payload.get("commits", [])

    if not commits:
        print("⚠️ No commits found in payload")
        return {"status": "no commits"}

    for commit in commits:
        result = analyze_commit(commit)

        print("\n📩 New Commit Received")
        print(f"  Message : {result['message']}")
        print(f"  Task ID : {result['task_id']}")
        print(f"  Intent  : {result['intent']}")
        print(f"  Areas   : {result['areas']}")

    return {"status": "processed"}
