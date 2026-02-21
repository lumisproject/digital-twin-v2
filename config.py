import os
from dotenv import load_dotenv

load_dotenv()

JIRA_CLIENT_ID = os.getenv("JIRA_CLIENT_ID")
JIRA_CLIENT_SECRET = os.getenv("JIRA_CLIENT_SECRET")
JIRA_REDIRECT_URI = os.getenv("JIRA_REDIRECT_URI", "http://localhost:8000/auth/jira/callback")

JIRA_AUTH_URL = "https://auth.atlassian.com/authorize"
JIRA_TOKEN_URL = "https://auth.atlassian.com/oauth/token"

# Base for accessible resources
JIRA_API_BASE = "https://api.atlassian.com"
# Base for instance actions
JIRA_API_BASE_URL = "https://api.atlassian.com/ex/jira"

# Add these to your existing config.py
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY") # e.g., for Gemini or OpenAI