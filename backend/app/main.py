from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, meta, repos
from app.core.cache import get_redis
from app.core.db import close_pool, get_pool, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_pool()


app = FastAPI(title="AI Trend Radar API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(repos.router, prefix="/api/v1")
app.include_router(meta.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    pool = await get_pool()
    await pool.fetchval("SELECT 1")
    await get_redis().ping()
    return {"status": "ready"}
