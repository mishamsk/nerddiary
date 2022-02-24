from fastapi import FastAPI

from .api.api_v1.routers.websocket import nds, websocket_router

app = FastAPI(title="NerdDiary Server", docs_url="/api/docs", openapi_url="/api.json")


@app.on_event("startup")
async def startup_event():
    await nds.astart()


@app.on_event("shutdown")
async def shutdown_event():
    await nds.aclose()


# Routers
app.include_router(websocket_router, prefix="/api/v1")
