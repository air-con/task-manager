from fastapi import FastAPI, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from loguru import logger

from . import services, clients, state
from .api import router as api_router, api_key_auth
from .scheduler import check_and_replenish_tasks
from .archiver import archive_completed_tasks
from .logging_config import setup_logging
from .config import settings

from momento import CacheClient, Configurations, CredentialProvider
from datetime import timedelta
import httpx

# Setup logging as the first step
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up the application...")
    
    # Initialize and store shared clients
    clients.httpx_client = httpx.AsyncClient()
    clients.momento_client = CacheClient(
        Configurations.Laptop.v1(), 
        CredentialProvider.from_string(settings.MOMENTO_API_KEY), 
        default_ttl=timedelta(days=365*10)
    )
    logger.info("HTTPX and Momento clients initialized.")

    # Initialize and start the scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_replenish_tasks, 'interval', hours=4)
    scheduler.add_job(archive_completed_tasks, 'cron', hour=3, minute=0)
    scheduler.start()
    logger.info("Scheduler started.")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await clients.httpx_client.aclose()
    clients.momento_client.close()
    scheduler.shutdown()
    logger.info("Clients and scheduler shut down gracefully.")

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
