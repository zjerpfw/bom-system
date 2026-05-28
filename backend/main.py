from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.paths import get_frontend_dist_dir
from app.services.material_service import load_index


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化数据库。"""
    await init_db()
    app.state.material_index, app.state.material_id_map = load_index()
    yield


app = FastAPI(title="BOM智能采集系统", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """校验API Key。"""
    settings = get_settings()
    if request.url.path.startswith("/api/") and settings.api_key:
        provided_key = request.headers.get("X-API-Key")
        if provided_key != settings.api_key:
            return JSONResponse(status_code=401, content={"code": 401, "msg": "invalid api key", "data": {}})
    return await call_next(request)


app.include_router(api_router, prefix="/api")

frontend_dist_dir = get_frontend_dist_dir()
if frontend_dist_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dist_dir, html=True), name="frontend")


if __name__ == "__main__":
    """EXE直接启动时运行内置Web服务。"""
    import uvicorn

    runtime_settings = get_settings()
    uvicorn.run(app, host=runtime_settings.host, port=runtime_settings.port)
