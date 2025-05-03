import os
from typing import Generator, Union
from groq import Groq
from groq.error import GroqError

# Initialize client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Production-only supported models, prioritized
GROQ_MODEL_PRIORITY = [
    "llama-3.3-70b-versatile",  # preferred
    "llama3-70b-8192",          # fallback 1
    "llama3-8b-8192",           # fallback 2
    "llama-3.1-8b-instant",     # fallback 3
    "llama-guard-3-8b",         # niche safety model fallback
    "gemma2-9b-it"              # last-resort general model
]

def call_groq(prompt: str, stream: bool = False) -> Union[str, Generator[str, None, None]]:
    """
    Send prompt to Groq, with optional streaming. Falls back to next model on failure.

    :param prompt: Prompt text for LLM
    :param stream: Whether to stream token output
    :return: Full response string or generator of streamed tokens
    """
    last_error = None

    for model in GROQ_MODEL_PRIORITY:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                stream=stream
            )

            if stream:
                # Return a generator of streamed tokens
                def stream_generator():
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content

                return stream_generator()
            else:
                # Return the full content as string
                return response.choices[0].message.content.strip()

        except GroqError as e:
            last_error = e
            print(f"[WARN] Model '{model}' failed. Trying fallback...")

    raise RuntimeError(f"All model fallbacks failed. Last error: {last_error}")
