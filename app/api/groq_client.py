import requests
import os

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def call_groq(prompt: str, model: str = "llama3-70b-8192") -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "stream": False
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # Raise an exception if Groq fails
    return response.json()
