from fastapi import FastAPI, Depends
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

from .api import router as api_router, api_key_auth
from .scheduler import check_and_replenish_tasks
from .logging_config import setup_logging

# Setup logging as the first step
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up the application...")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_replenish_tasks, 'interval', hours=4)
    scheduler.start()
    logger.info("Scheduler started. Will run every 4 hours.")
    yield
    # Shutdown
    logger.info("Shutting down...")
    scheduler.shutdown()

app = FastAPI(
    title="Task Manager",
    description="A service to manage MQ tasks with Feishu Bitable as a database.",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(api_router, prefix="/api", tags=["Tasks"], dependencies=[Depends(api_key_auth)])

@app.get("/")
async def root():
    return {"message": "Task Manager is running."}
