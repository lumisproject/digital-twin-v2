import time
import requests
import json
import os
from config import JIRA_CLIENT_ID, JIRA_CLIENT_SECRET, JIRA_TOKEN_URL

# File-based store to persist across restarts
TOKEN_FILE = "jira_tokens.json"

def load_all_tokens() -> dict:
    """Loads all tokens from the local JSON file."""
    if not os.path.exists(TOKEN_FILE):
        return {}
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_tokens(user_id: str, tokens: dict):
    """Saves tokens for a specific user to the local JSON file."""
    all_tokens = load_all_tokens()
    
    # Calculate expiration time (current time + expires_in seconds)
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
    all_tokens[user_id] = tokens
    
    with open(TOKEN_FILE, "w") as f:
        json.dump(all_tokens, f, indent=4)

def refresh_jira_token(user_id: str):
    """Uses the refresh token to get a new access token and updates the file."""
    all_tokens = load_all_tokens()
    tokens = all_tokens.get(user_id)
    
    if not tokens or "refresh_token" not in tokens:
        return None

    payload = {
        "grant_type": "refresh_token",
        "client_id": JIRA_CLIENT_ID,
        "client_secret": JIRA_CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"]
    }

    response = requests.post(JIRA_TOKEN_URL, json=payload)
    if response.status_code == 200:
        new_tokens = response.json()
        # Maintain the existing refresh token if a new one isn't provided
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = tokens["refresh_token"]
        
        save_tokens(user_id, new_tokens)
        return new_tokens["access_token"]
    return None

def get_valid_token(user_id: str):
    """Retrieves a valid token from the file, refreshing it if nearly expired."""
    all_tokens = load_all_tokens()
    tokens = all_tokens.get(user_id)
    
    if not tokens:
        return None

    # Refresh if token is within 60 seconds of expiring
    if time.time() > (tokens["expires_at"] - 60):
        return refresh_jira_token(user_id)
    
    return tokens["access_token"]

def is_connected(user_id: str) -> bool:
    """Checks if a user has a stored token in the file."""
    all_tokens = load_all_tokens()
    return user_id in all_tokens