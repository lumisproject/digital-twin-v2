import google.generativeai as genai
import json
from config import AI_API_KEY

genai.configure(api_key=AI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

def analyze_fulfillment(issue, code_diff):
    """Uses AI to determine if the code diff satisfies the Jira issue requirements."""
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
    
    response = model.generate_content(prompt)
    try:
        # Clean response if AI includes markdown code blocks
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except:
        return {"status": "INCOMPLETE", "summary": "AI could not parse response.", "new_tasks": []}