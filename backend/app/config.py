import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://research:research@localhost:5433/research")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_TTL_HOURS = 24 * 7

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.x.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "grok-4-fast-non-reasoning")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"   # 384 dimensions, runs locally for free
