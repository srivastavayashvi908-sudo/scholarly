"""LLM calls via any OpenAI-compatible API (Groq by default)."""
from fastapi import HTTPException

from ..config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def chat(system: str, user: str, max_tokens: int = 2500, reasoning_effort: str | None = None) -> str:
    """`reasoning_effort` ("low"/"medium"/"high") limits how long reasoning models think first,
    leaving more of the token budget for the answer itself."""
    if not LLM_API_KEY:
        raise HTTPException(503, "No LLM API key configured. Add LLM_API_KEY to the .env file and restart.")
    from openai import APIStatusError, OpenAI, OpenAIError

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=120)
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else None
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body=extra,
        )
    except APIStatusError as e:
        if e.status_code in (413, 429):   # free tiers cap tokens per minute
            raise HTTPException(429, "The AI's free usage limit was reached for this minute. Wait about a minute and try again.")
        raise HTTPException(502, f"LLM request failed: {e}")
    except OpenAIError as e:
        raise HTTPException(502, f"LLM request failed: {e}")
    return (resp.choices[0].message.content or "").strip()
