import json
import os
from openai import OpenAI
from config import AI_API_KEY

# OpenRouter client setup
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=AI_API_KEY,
)

# Use the model you selected
MODEL_ID = os.getenv("AI_MODEL", "stepfun/step-3.5-flash:free")

def analyze_fulfillment(issue, code_diff):
    """Dynamically analyzes the provided issue and code diff."""
    
    # Extract details from the Jira issue object
    summary = issue.get("fields", {}).get("summary", "No Summary")
    description = issue.get("fields", {}).get("description", "No Description")
    
    # Construct the prompt using the function arguments
    prompt = f"""
    You are a Senior Technical Lead. Compare the Jira Task requirements against the actual Code Changes provided.
    
    JIRA TASK SUMMARY: {summary}
    JIRA TASK DESCRIPTION: {description}
    
    CODE CHANGES (DIFF):
    {code_diff}
    
    Respond STRICTLY in JSON format with:
    1. "status": "COMPLETE" if the code changes fully satisfy the Jira task, otherwise "INCOMPLETE".
    2. "summary": A professional explanation of your decision for the developer.
    3. "new_tasks": A list of objects with "title" and "description" for any missing features or bugs found.
    """
    
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
        )
        
        content = response.choices[0].message.content
        # Remove potential markdown formatting from AI response
        clean_json = content.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        print(f"AI Engine Error: {e}")
        return {
            "status": "INCOMPLETE", 
            "summary": f"AI analysis failed: {str(e)}", 
            "new_tasks": []
        }