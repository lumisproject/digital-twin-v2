from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from github_webhook import github_router
from jira_oauth import (
    build_auth_url,
    exchange_code_for_token,
    get_accessible_resources
)
from token_store import is_connected

app = FastAPI(title="Lumis Intelligence Orchestrator")

# Register GitHub webhook routes
app.include_router(github_router)

templates = Jinja2Templates(directory="templates")

# TEMP user (replace later with real auth)
USER_ID = "demo-user"

@app.get("/")
def health_check():
    return {"status": "running"}

# Optional UI
@app.get("/ui", response_class=HTMLResponse)
def ui(request: Request):
    status = "Connected ✅" if is_connected(USER_ID) else "Not Connected ❌"
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "status": status}
    )

# Step 1 — Start Jira OAuth
@app.get("/auth/jira/connect")
def connect_jira():
    auth_url = build_auth_url(USER_ID)
    return RedirectResponse(auth_url)

# Step 2 — Jira OAuth callback
@app.get("/auth/jira/callback")
def jira_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        return {"error": "Missing code or state"}

    tokens = exchange_code_for_token(code, state)
    sites = get_accessible_resources(tokens["access_token"])

    return {
        "message": "Jira connected successfully",
        "sites": sites
    }


# test XD