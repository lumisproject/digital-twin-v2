from fastapi import FastAPI
from github_webhook import github_router

app = FastAPI(title="Lumis Intelligence Orchestrator")

# Register GitHub webhook routes
app.include_router(github_router)

@app.get("/")
def health_check():
    return {"status": "running"}








#<!-- webhook test 4 -->
