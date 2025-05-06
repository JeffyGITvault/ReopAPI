import os
import logging
from typing import Generator, Union, Optional
from groq import Groq

logger = logging.getLogger(__name__)

def get_groq_client() -> Groq:
    """
    Safely initialize and return a Groq client using the GROQ_API_KEY environment variable.
    Raises an error if the key is missing.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY environment variable is not set.")
        raise RuntimeError("GROQ_API_KEY environment variable is not set.")
    return Groq(api_key=api_key)

client = get_groq_client()

# Production-only supported models, prioritized
GROQ_MODEL_PRIORITY = [
    "llama-3.3-70b-versatile",  # preferred
    "llama3-70b-8192",          # fallback 1
    "llama3-8b-8192",           # fallback 2
    "llama-3.1-8b-instant",     # fallback 3
    "llama-guard-3-8b",         # niche safety model fallback
    "gemma2-9b-it"              # last-resort general model
]

def call_groq(prompt: str, stream: bool = False, max_tokens: Optional[int] = 8192) -> Union[str, Generator[str, None, None]]:
    """
    Send prompt to Groq, with optional streaming. Falls back to next model on failure.

    :param prompt: Prompt text for LLM
    :param stream: Whether to stream token output
    :param max_tokens: Maximum number of tokens for completion (default 8192)
    :return: Full response string or generator of streamed tokens
    """
    last_error = None
    for model in GROQ_MODEL_PRIORITY:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                stream=stream,
                max_tokens=max_tokens
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
        except Exception as e:
            last_error = e
            logger.warning(f"[WARN] Model '{model}' failed. Trying fallback... Error: {e}")
    raise RuntimeError(f"All model fallbacks failed. Last error: {last_error}")
