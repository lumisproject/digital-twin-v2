import re

TASK_ID_REGEX = r"\b[A-Z]{2,10}-\d+\b"

def extract_task_id(message: str):
    match = re.search(TASK_ID_REGEX, message)
    return match.group(0) if match else None


def detect_intent(message: str):
    msg = message.lower()

    if any(w in msg for w in ["fix", "bug", "hotfix", "patch"]):
        return "bugfix"
    if any(w in msg for w in ["add", "implement", "create"]):
        return "feature"
    if any(w in msg for w in ["refactor", "cleanup", "restructure"]):
        return "refactor"
    if any(w in msg for w in ["test", "spec"]):
        return "test"

    return "unknown"


def detect_areas(files):
    areas = set()

    for f in files:
        f = f.lower()
        if "auth" in f:
            areas.add("authentication")
        if "api" in f or "backend" in f:
            areas.add("backend")
        if "ui" in f or "frontend" in f:
            areas.add("frontend")
        if "db" in f or "database" in f:
            areas.add("database")

    return list(areas)


def analyze_commit(commit: dict):
    message = commit.get("message", "")
    files = (
        commit.get("added", [])
        + commit.get("modified", [])
        + commit.get("removed", [])
    )

    return {
        "message": message,
        "task_id": extract_task_id(message),
        "intent": detect_intent(message),
        "areas": detect_areas(files),
    }
