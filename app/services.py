import httpx
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *
from typing import List, Dict, Any, TypedDict
from enum import Enum

# --- Type Definitions ---

class StatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class BitableRecord(TypedDict):
    id: str
    status: StatusEnum
    payload: str

class BitableUpdate(TypedDict):
    record_id: str
    fields: Dict[str, Any]

from celery import Celery

from .config import settings

# Initialize Celery App
celery_app = Celery(settings.CELERY_APP_NAME, broker=settings.CELERY_BROKER_URL)

# Initialize Lark Client
# The client needs to be properly initialized. Using an async context for client methods.

def get_lark_client():
    return lark.Client.builder() \
        .app_id(settings.FEISHU_APP_ID) \
        .app_secret(settings.FEISHU_APP_SECRET) \
        .build()

# --- Bitable (Database) Operations ---



async def add_records_to_bitable(records: List[BitableRecord]) -> List[Dict[str, Any]]:
    """
    Adds a list of records to the Feishu Bitable.
    """
    client = get_lark_client()
    request = BatchCreateAppTableRecordRequest.builder() \
        .app_token(settings.FEISHU_BITABLE_APP_TOKEN) \
        .table_id(settings.FEISHU_BITABLE_TABLE_ID) \
        .request_body(BatchCreateAppTableRecordRequestBody.builder()
            .records([AppTableRecord.builder().fields(rec).build() for rec in records])
            .build()) \
        .build()
    
    response = await client.bitable.v1.app_table_record.abatch_create(request)
    if not response.success():
        raise Exception(f"Failed to add records to Bitable: {response.msg}")
    return response.data.records

async def update_records_in_bitable(updates: List[BitableUpdate]):
    """
    Updates records in the Bitable. Each update needs a record_id.
    """
    client = get_lark_client()
    request_records = [
        UpdateAppTableRecordRequest.builder().record_id(upd["record_id"]).fields(upd["fields"]).build() for upd in updates
    ]
    
    request = BatchUpdateAppTableRecordRequest.builder() \
        .app_token(settings.FEISHU_BITABLE_APP_TOKEN) \
        .table_id(settings.FEISHU_BITABLE_TABLE_ID) \
        .request_body(BatchUpdateAppTableRecordRequestBody.builder()
            .records(request_records)
            .build()) \
        .build()

    response = await client.bitable.v1.app_table_record.abatch_update(request)
    if not response.success():
        raise Exception(f"Failed to update records in Bitable: {response.msg}")
    return response.data.records

async def add_single_record(record: BitableRecord) -> bool:
    """
    Adds a single record to the Feishu Bitable.
    Returns True if successful, False if it was a duplicate.
    Raises an exception for other errors.
    """
    try:
        await add_records_to_bitable([record])
        return True
    except Exception as e:
        # A bit fragile, but the SDK doesn't provide structured errors here.
        if "duplicate" in str(e).lower():
            return False
        # For other errors, we should not suppress them.
        raise e

async def get_pending_tasks_from_bitable(count: int) -> List[Dict[str, Any]]:
    """
    Gets a specified number of tasks with 'PENDING' status.
    """
    client = get_lark_client()
    request = ListAppTableRecordRequest.builder()         .app_token(settings.FEISHU_BITABLE_APP_TOKEN)         .table_id(settings.FEISHU_BITABLE_TABLE_ID)         .filter('CurrentValue.[status] = "PENDING"')         .page_size(count)         .build()
        
    response = await client.bitable.v1.app_table_record.alist(request)
    if not response.success():
        raise Exception(f"Failed to get pending tasks: {response.msg}")
    
    return [{"record_id": r.record_id, **r.fields} for r in response.data.items]

# --- Celery Publisher & Notification Operations ---

def publish_to_celery(tasks: Any, priority: int = None):
    """
    Publishes tasks directly to Celery.
    """
    celery_app.send_task(
        name=settings.CELERY_TASK_NAME,
        args=[tasks],
        queue=settings.CELERY_QUEUE,
        priority=priority
    )
    task_count = len(tasks) if isinstance(tasks, list) else 1
    priority_str = f" with priority {priority}" if priority is not None else ""
    print(f"Sent {task_count} tasks to Celery queue '{settings.CELERY_QUEUE}'{priority_str}.")

from . import state

async def send_feishu_notification(message: str):
    """
    Sends a notification to a Feishu group using a robot webhook.
    """
    if not state.NOTIFICATIONS_ENABLED:
        return

    if not settings.FEISHU_ROBOT_WEBHOOK_URL:
        print("FEISHU_ROBOT_WEBHOOK_URL not set, skipping notification.")
        return

    async with httpx.AsyncClient() as client:
        payload = {
            "msg_type": "text",
            "content": {"text": message}
        }
        try:
            response = await client.post(settings.FEISHU_ROBOT_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        except httpx.RequestError as e:
            print(f"Failed to send Feishu notification: {e}")