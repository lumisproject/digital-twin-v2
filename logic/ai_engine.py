import json
import os
from openai import OpenAI
from config import AI_API_KEY

# OpenRouter requires the base_url to be redirected
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=AI_API_KEY,
)

MODEL_ID = os.getenv("AI_MODEL", "stepfun/step-3.5-flash:free")

def analyze_fulfillment(issue, code_diff):
    """Uses OpenRouter to determine if the task is fulfilled."""
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
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
        )
        
        content = response.choices[0].message.content
        # Clean response if AI includes markdown code blocks
        clean_json = content.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        print(f"AI Engine Error: {e}")
        return {"status": "INCOMPLETE", "summary": "AI could not parse response.", "new_tasks": []}