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
from .feishu_sync import sync_feishu_task_results
from .logging_config import setup_logging
from .config import get_settings

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
    settings = get_settings()
    clients.httpx_client = httpx.AsyncClient()
    clients.momento_client = CacheClient(
        Configurations.Laptop.v1(), 
        CredentialProvider.from_string(settings.MOMENTO_API_KEY), 
        default_ttl=timedelta(days=365*10)
    )
    clients.supabase_headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    logger.info("HTTPX, Momento, and Supabase clients initialized.")

    # Initialize and start the scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_replenish_tasks, 'interval', hours=4)
    # Schedule the daily archival job to run at a low-traffic time, e.g., 3 AM UTC
    scheduler.add_job(archive_completed_tasks, 'cron', hour=3, minute=0)
    # Schedule the Feishu sync job to run every hour
    scheduler.add_job(sync_feishu_task_results, 'interval', hours=1)
    
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
async def get_status_page(request: Request, peek: bool = False):
    """
    Serves the status dashboard page. Can optionally peek at a message from the MQ.
    """
    settings = get_settings()
    mq_task_count = services.get_mq_queue_size(settings.CELERY_QUEUE)
    pending_tasks_db_count = await services.get_pending_tasks_count()
    
    peeked_message = None
    if peek:
        peeked_message = services.peek_mq_message(settings.CELERY_QUEUE)

    return templates.TemplateResponse("status.html", {
        "request": request,
        "mq_task_count": mq_task_count,
        "pending_tasks_db": pending_tasks_db_count,
        "peeked_message": peeked_message,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.get("/")
async def root():
    return {"message": "Task Manager is running."}
