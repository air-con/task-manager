from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

from .api import router as api_router, api_key_auth
from .scheduler import check_and_replenish_tasks
from .archiver import archive_completed_tasks
from .logging_config import setup_logging
from . import services

# Setup logging as the first step
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up the application...")
    scheduler = AsyncIOScheduler()
    # Schedule the main task replenishment job
    scheduler.add_job(check_and_replenish_tasks, 'interval', hours=4)
    # Schedule the daily archival job to run at a low-traffic time, e.g., 3 AM UTC
    scheduler.add_job(archive_completed_tasks, 'cron', hour=3, minute=0)
    
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

# --- UI Endpoint ---

templates = Jinja2Templates(directory="templates")

@app.get("/status", response_class=HTMLResponse)
async def get_status_page(request: Request):
    """
    Serves the status dashboard page.
    """
    mq_task_count = services.get_mq_queue_size(settings.CELERY_QUEUE)
    pending_tasks = await services.get_pending_tasks(count=100000) # Get a high number for an accurate count
    
    return templates.TemplateResponse("status.html", {
        "request": request,
        "mq_task_count": mq_task_count,
        "pending_tasks_db": len(pending_tasks),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.get("/")
async def root():
    return {"message": "Task Manager is running."}
