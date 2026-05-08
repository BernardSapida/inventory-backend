from fastapi import FastAPI
from loguru import logger
from fastapi.middleware.cors import CORSMiddleware

from routes.inventory import router as inventory_router
from routes.scan import router as scan_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inventory_router)
app.include_router(scan_router)

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Server started!")
    logger.info("📦 Inventory routes loaded!")
    logger.info("📷 Scan routes loaded!")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Server shutting down!")

@app.get("/")
def read_root():
    logger.info("✅ Health check endpoint called!")
    return {"message": "Inventory Backend is running!"}