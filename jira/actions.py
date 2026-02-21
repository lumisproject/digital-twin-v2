import requests
from jira.client import jira_headers

def add_comment(cloud_id: str, issue_key: str, comment: str, access_token: str):
    """Adds a comment to an issue."""
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue/{issue_key}/comment"
    payload = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}]
        }
    }
    requests.post(url, headers=jira_headers(access_token), json=payload).raise_for_status()

def transition_issue(cloud_id: str, issue_key: str, transition_name: str, access_token: str):
    """Moves an issue to a new status by name (e.g., 'In Progress')."""
    # 1. Fetch available transitions to find the ID for the given name
    base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue/{issue_key}/transitions"
    res = requests.get(base_url, headers=jira_headers(access_token))
    res.raise_for_status()
    
    transitions = res.json().get("transitions", [])
    # Find the transition matching your target status name
    target = next((t for t in transitions if t["name"].lower() == transition_name.lower()), None)
    
    if not target:
        print(f"Transition '{transition_name}' not available for {issue_key}")
        return

    # 2. Execute the transition
    payload = {"transition": {"id": target["id"]}}
    requests.post(base_url, headers=jira_headers(access_token), json=payload).raise_for_status()

def create_issue(cloud_id: str, project_key: str, summary: str, description: str, access_token: str):
    """Creates a new Jira issue."""
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            },
            "issuetype": {"name": "Task"}
        }
    }
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()