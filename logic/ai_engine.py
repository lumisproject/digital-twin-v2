from google import genai
import json
from config import AI_API_KEY

# Initialize the new Client
client = genai.Client(api_key=AI_API_KEY)
MODEL_ID = "gemini-2.0-flash" # Use the latest stable model

def analyze_fulfillment(issue, code_diff):
    """Uses the new google.genai SDK to determine if the task is fulfilled."""
    prompt = f"""
    You are a Senior Technical Lead. Compare the Jira Task description against the Code Changes.
    
    Jira Task: {issue['fields']['summary']}
    Description: {issue['fields'].get('description', 'No description provided')}
    
    Code Changes:
    {code_diff}
    
    Respond STRICTLY in JSON format with:
    1. "status": "COMPLETE" if all requirements are met, or "INCOMPLETE".
    2. "summary": A brief explanation of your decision.
    3. "new_tasks": A list of objects with "title" and "description" for any missing features or bugs found.
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        
        # Clean response if AI includes markdown code blocks
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        print(f"AI Engine Error: {e}")
        return {"status": "INCOMPLETE", "summary": "AI could not parse response.", "new_tasks": []}