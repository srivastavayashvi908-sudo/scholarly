import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

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

for module in (auth, papers, highlights, notes, comments, collections, concepts, citations,
               ai, search, reading, stats, recommendations):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
