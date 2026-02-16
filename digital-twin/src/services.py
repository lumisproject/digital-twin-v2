import os
import hashlib
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY= os.getenv("OPENROUTER_API_KEY")
LLM_MODEL = os.getenv("MODEL")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=LLM_API_KEY,
)

# Load once, use everywhere
embed_model = SentenceTransformer('all-MiniLM-L6-v2')

def get_llm_completion(system_prompt, user_prompt, temperature=0.2):
    try:
        completion = client.chat.completions.create(
            extra_body={"reasoning": {"enabled": True}},
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        return None

def get_embedding(text):
    return embed_model.encode(text).tolist()

def generate_footprint(text):
    """Creates a unique SHA-256 hash for a string of code."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()