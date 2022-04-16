from fastapi import FastAPI

from .api.api_v1.routers.logs import logs_router
from .api.api_v1.routers.session import session_router
from .api.api_v1.routers.websocket import websocket_router
from .dependencies import nds

app = FastAPI(title="NerdDiary Server", docs_url="/api/docs", openapi_url="/api.json")


@app.on_event("startup")
async def startup_event():
    await nds.astart()


@app.on_event("shutdown")
async def shutdown_event():
    await nds.aclose()


# Routers
app.include_router(websocket_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")
app.include_router(logs_router, prefix="/api/v1")
