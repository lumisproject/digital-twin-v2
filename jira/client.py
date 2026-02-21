import requests

def jira_headers(access_token: str):
    """Standard headers for Atlassian API."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def get_issue(cloud_id: str, issue_key: str, access_token: str):
    """Fetches full issue data including status."""
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue/{issue_key}"
    response = requests.get(url, headers=jira_headers(access_token))
    response.raise_for_status()
    return response.json()

def get_issue_details(cloud_id: str, issue_key: str, access_token: str):
    """Specifically fetches summary and description for AI analysis."""
    # We use rest/api/3/issue/{key}?fields=summary,description
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue/{issue_key}?fields=summary,description,status"
    response = requests.get(url, headers=jira_headers(access_token))
    response.raise_for_status()
    return response.json()

def get_accessible_resources(access_token: str):
    """Retrieves list of Jira sites to find the cloud_id."""
    url = "https://api.atlassian.com/oauth/token/accessible-resources"
    response = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
    response.raise_for_status()
    return response.json()