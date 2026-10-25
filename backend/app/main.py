import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .db import pool, run_migrations
from .routes import (ai, auth, citations, collections, comments, concepts, highlights, notes, papers,
                     reading, recommendations, search, stats)
from .services import embeddings


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    pool.open()
    # Load the embedding model in the background so the first save isn't slow.
    threading.Thread(target=embeddings.warm_up, daemon=True).start()
    yield
    pool.close()


app = FastAPI(title="Scholarly", lifespan=lifespan)

if CORS_ORIGINS:
    # Only needed when the frontend is served from a different site (e.g. Vercel).
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for module in (auth, papers, highlights, notes, comments, collections, concepts, citations,
               ai, search, reading, stats, recommendations):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
