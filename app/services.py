from loguru import logger
from typing import List, Dict, Any, TypedDict, Union
from enum import Enum
import httpx
from celery import Celery

from .config import settings
from . import state

# --- Type Definitions ---

class StatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class TaskRecord(TypedDict):
    id: str
    status: str
    payload: str

class TaskUpdate(TypedDict):
    record_id: str
    fields: Dict[str, Any]

# --- Client Initializations ---

celery_app = Celery(settings.CELERY_APP_NAME, broker=settings.CELERY_BROKER_URL)

# --- Database Operations (Async Supabase) ---

async def _get_supabase_headers() -> Dict[str, str]:
    return {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

async def add_tasks(records: List[TaskRecord]) -> List[Dict[str, Any]]:
    """
    Adds or updates a list of records in the Supabase 'tasks' table using async HTTP.
    """
    headers = await _get_supabase_headers()
    url = f"{settings.SUPABASE_URL}/rest/v1/tasks"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=records, params={"on_conflict": "id"})
            response.raise_for_status()
            logger.info(f"Successfully upserted {len(response.json())} records.")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error while adding tasks to Supabase: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to add records to Supabase: {e}")
            raise

async def update_tasks(updates: List[TaskUpdate]):
    """
    Updates records in the Supabase 'tasks' table using async HTTP.
    """
    headers = await _get_supabase_headers()
    async with httpx.AsyncClient() as client:
        for update in updates:
            url = f"{settings.SUPABASE_URL}/rest/v1/tasks?id=eq.{update['record_id']}"
            try:
                await client.patch(url, headers=headers, json=update['fields'])
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error updating task {update['record_id']}: {e.response.text}")
                # Decide if you want to raise or just log and continue
            except Exception as e:
                logger.error(f"Failed to update task {update['record_id']}: {e}")
        logger.info(f"Processed {len(updates)} updates.")

async def get_pending_tasks(count: int) -> List[Dict[str, Any]]:
    """
    Gets a specified number of tasks with 'PENDING' status from Supabase using async HTTP.
    """
    headers = await _get_supabase_headers()
    url = f"{settings.SUPABASE_URL}/rest/v1/tasks"
    params = {"status": "eq.PENDING", "limit": str(count), "select": "*"}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting pending tasks: {e.response.text}")
        except Exception as e:
            logger.error(f"Failed to get pending tasks from Supabase: {e}")
        return []

def create_task_records(data: List[Dict[str, Any]], status: StatusEnum) -> List[TaskRecord]:
    """
    Creates a list of task records from raw data, including hashing for the ID.
    """
    records_to_add = []
    for item in data:
        payload_json = json.dumps(item, sort_keys=True, ensure_ascii=False)
        identifier = hashlib.md5(payload_json.encode()).hexdigest()
        records_to_add.append({
            "id": identifier,
            "status": status.value,
            "payload": payload_json
        })
    return records_to_add

# --- MQ & Notification Operations ---

def get_mq_queue_size(queue_name: str) -> int:
    """
    Gets the number of messages in a specific RabbitMQ queue.
    Returns -1 if an error occurs.
    """
    try:
        with celery_app.connection_for_read() as conn:
            with conn.channel() as channel:
                _, message_count, _ = channel.queue_declare(queue=queue_name, passive=True)
                return message_count
    except Exception as e:
        logger.error(f"Could not connect to RabbitMQ or get queue size for '{queue_name}'. Error: {e}")
        return -1

def publish_to_celery(tasks: Union[Dict[str, Any], List[Dict[str, Any]]], priority: int = None):
    """
    Publishes tasks to Celery, optimizing for a single task.
    """
    task_to_send = tasks
    task_count = 1

    if isinstance(tasks, list):
        if len(tasks) == 1:
            task_to_send = tasks[0]
        task_count = len(tasks)

    celery_app.send_task(
        name=settings.CELERY_TASK_NAME,
        args=[task_to_send],
        queue=settings.CELERY_QUEUE,
        priority=priority
    )
    
    priority_str = f" with priority {priority}" if priority is not None else ""
    logger.info(f"Sent {task_count} task(s) to Celery queue '{settings.CELERY_QUEUE}'{priority_str}.")

async def send_feishu_notification(message: str):
    """
    Sends a notification to a Feishu group using a robot webhook.
    """
    if not state.NOTIFICATIONS_ENABLED:
        return
    
    webhook_url = settings.FEISHU_ROBOT_WEBHOOK_URL
    if not webhook_url:
        logger.warning("FEISHU_ROBOT_WEBHOOK_URL not set, skipping notification.")
        return

    async with httpx.AsyncClient() as client:
        payload = {"msg_type": "text", "content": {"text": message}}
        try:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        except httpx.RequestError as e:
            logger.error(f"Failed to send Feishu notification: {e}")