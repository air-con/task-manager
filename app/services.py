from loguru import logger
from typing import List, Dict, Any, TypedDict, Union
from enum import Enum
import httpx
from datetime import datetime
import hashlib
import json
from celery import Celery

from .config import get_settings
from . import clients, state
from .schemas import StatusEnum, TaskRecord, TaskUpdate

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

celery_app = Celery(get_settings().CELERY_APP_NAME, broker=get_settings().CELERY_BROKER_URL)

# --- Database Operations (Async Supabase) ---

async def _get_supabase_headers(prefer_return: bool = True) -> Dict[str, str]:
    """Constructs headers for a Supabase request, with optional 'Prefer' header."""
    headers = clients.supabase_headers.copy()
    if prefer_return:
        headers["Prefer"] = "return=representation"
    return headers

async def add_tasks(records: List[TaskRecord]) -> List[Dict[str, Any]]:
    """
    Adds or updates a list of records in the Supabase 'tasks' table using a shared httpx client.
    """
    headers = await _get_supabase_headers()
    url = f"{get_settings().SUPABASE_URL}/rest/v1/tasks"
    
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
        url = f"{get_settings().SUPABASE_URL}/rest/v1/tasks?id=eq.{update['record_id']}"
        try:
            await clients.httpx_client.patch(url, headers=headers, json=update['fields'])
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error updating task {update['record_id']}: {e.response.text}")

async def get_pending_tasks(count: int) -> List[Dict[str, Any]]:
    """
    Gets a specified number of tasks with 'PENDING' status from Supabase using a shared httpx client.
    """
    headers = await _get_supabase_headers()
    url = f"{get_settings().SUPABASE_URL}/rest/v1/tasks"
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
    settings = get_settings()
    headers = await _get_supabase_headers()
    url = f"{settings.SUPABASE_URL}/rest/v1/tasks"
    params = {
        "select": "id",
        "status": "in.(SUCCESS,FAILED)",
        "updated_at": f"lte.{timestamp.isoformat()}"
    }
    try:
        response = await clients.httpx_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting completed tasks: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to get completed tasks from Supabase: {e}")
    return []

async def get_pending_tasks_count() -> int:
    """
    Gets the count of tasks with 'PENDING' status from Supabase efficiently.
    """
    settings = get_settings()
    headers = await _get_supabase_headers(prefer_return=False)
    headers["Prefer"] = "count=exact"
    url = f"{get_settings().SUPABASE_URL}/rest/v1/tasks"
    params = {"status": "eq.PENDING", "limit": "1"} # Limit 1 is needed for count
    
    try:
        response = await clients.httpx_client.head(url, headers=headers, params=params)
        response.raise_for_status()
        content_range = response.headers.get("content-range")
        if content_range:
            return int(content_range.split('/')[1])
        return 0
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting pending task count: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to get pending task count from Supabase: {e}")
    return -1 # Return -1 to indicate an error

async def delete_tasks(ids: List[str]):
    """
    Deletes tasks from Supabase by their IDs without returning the data.
    """
    headers = await _get_supabase_headers(prefer_return=False)
    url = f"{get_settings().SUPABASE_URL}/rest/v1/tasks"
    params = {"id": f"in.({','.join(ids)})"}
    try:
        response = await clients.httpx_client.delete(url, headers=headers, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error while deleting tasks: {e.response.text}")
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

def peek_mq_message(queue_name: str) -> Any:
    """
    Non-destructively peeks at the first message in the queue.
    It gets a message, decodes it, and then rejects it to re-queue it.
    Returns the message body or None if the queue is empty.
    """
    try:
        with celery_app.connection_for_read() as conn:
            with conn.channel() as channel:
                message = channel.basic_get(queue=queue_name, no_ack=False)
                if message is None:
                    logger.info(f"Queue '{queue_name}' is empty. Nothing to peek.")
                    return None

                # Decode the message body
                decoded_body = json.loads(message.body.decode())
                logger.info(f"Peeked at message in queue '{queue_name}'. Re-queueing.")

                # Re-queue the message by rejecting it
                channel.basic_reject(delivery_tag=message.delivery_tag, requeue=True)
                
                return decoded_body

    except Exception as e:
        logger.error(f"Could not peek at MQ queue '{queue_name}'. Error: {e}")
        return None

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

