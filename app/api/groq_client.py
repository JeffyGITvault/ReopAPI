import os
import logging
from typing import Generator, Union, Optional, List
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

# Short, focused list of agentic/web-search-enabled models per Groq docs
GROQ_MODEL_PRIORITY = [
    "compound-beta",            # primary, most capable
    "llama-3.3-70b-versatile",  # fallback if primary is down
    "meta-llama/llama-4-maverick-17b-128e-instruct", # additional fallback
]

def call_groq(
    prompt: str,
    stream: bool = False,
    max_tokens: Optional[int] = 8192,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    **kwargs
) -> Union[str, Generator[str, None, None]]:
    """
    Send prompt to Groq, with optional streaming and agentic tooling. Falls back to next model on failure.

    :param prompt: Prompt text for LLM
    :param stream: Whether to stream token output
    :param max_tokens: Maximum number of tokens for completion (default 8192)
    :param include_domains: List of domains to include in web search (e.g., ["sec.gov"])
    :param exclude_domains: List of domains to exclude from web search
    :param kwargs: Additional parameters for Groq API
    :return: Full response string or generator of streamed tokens
    """
    last_error = None
    for model in GROQ_MODEL_PRIORITY:
        try:
            logger.info(f"Calling Groq model: {model} (max_tokens={max_tokens})")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                stream=stream,
                max_tokens=max_tokens,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                **kwargs
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
    logger.error(f"All Groq model fallbacks failed. Last error: {last_error}")
    raise RuntimeError(f"All Groq model fallbacks failed. Last error: {last_error}")
