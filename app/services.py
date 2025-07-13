from loguru import logger
from typing import List, Dict, Any, TypedDict, Union
from enum import Enum
import httpx
from datetime import datetime
import hashlib
import json
from celery import Celery

from .config import settings
from . import clients, state

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
    Adds or updates a list of records in the Supabase 'tasks' table using a shared httpx client.
    """
    headers = await _get_supabase_headers()
    url = f"{config.settings.SUPABASE_URL}/rest/v1/tasks"
    
    try:
        response = await clients.httpx_client.post(url, headers=headers, json=records, params={"on_conflict": "id"})
        response.raise_for_status()
        logger.info(f"Successfully upserted {len(response.json())} records.")
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while adding tasks to Supabase: {e.response.text}")
        raise

async def update_tasks(updates: List[TaskUpdate]):
    """
    Updates records in the Supabase 'tasks' table using a shared httpx client.
    """
    headers = await _get_supabase_headers()
    for update in updates:
        url = f"{config.settings.SUPABASE_URL}/rest/v1/tasks?id=eq.{update['record_id']}"
        try:
            await clients.httpx_client.patch(url, headers=headers, json=update['fields'])
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error updating task {update['record_id']}: {e.response.text}")

async def get_pending_tasks(count: int) -> List[Dict[str, Any]]:
    """
    Gets a specified number of tasks with 'PENDING' status from Supabase using a shared httpx client.
    """
    headers = await _get_supabase_headers()
    url = f"{config.settings.SUPABASE_URL}/rest/v1/tasks"
    params = {"status": "eq.PENDING", "limit": str(count), "select": "*"}
    
    try:
        response = await clients.httpx_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting pending tasks: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to get pending tasks from Supabase: {e}")
    return []

async def get_completed_tasks_before(timestamp: datetime) -> List[Dict[str, Any]]:
    """
    Gets tasks that were completed (SUCCESS or FAILED) before a given timestamp.
    """
    try:
        response = await supabase.table('tasks').select("id").in_('status', ['SUCCESS', 'FAILED']).lte('updated_at', timestamp.isoformat()).execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to get completed tasks from Supabase: {e}")
        return []

async def delete_tasks(ids: List[str]) -> List[Dict[str, Any]]:
    """
    Deletes tasks from Supabase by their IDs.
    """
    try:
        response = supabase.table('tasks').delete().in_('id', ids).execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to delete tasks from Supabase: {e}")
        raise

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

