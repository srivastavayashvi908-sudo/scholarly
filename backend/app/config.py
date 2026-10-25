import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://research:research@localhost:5433/research")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_TTL_HOURS = 24 * 7

# Comma-separated list of sites allowed to call the API from a browser (the hosted frontend).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"   # 384 dimensions, runs locally for free
