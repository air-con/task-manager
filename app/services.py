import httpx
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *
from typing import List, Dict, Any
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

async def check_duplicate(task_identifier: str) -> bool:
    """
    Checks if a task with the given identifier already exists in the Bitable.
    Assumes a field named "Identifier" exists for this purpose.
    """
    client = get_lark_client()
    try:
        request = ListAppTableRecordRequest.builder() \
            .app_token(settings.FEISHU_BITABLE_APP_TOKEN) \
            .table_id(settings.FEISHU_BITABLE_TABLE_ID) \
            .filter(f'CurrentValue.[Identifier] = "{task_identifier}"') \
            .page_size(1) \
            .build()
        
        response = await client.bitable.v1.app_table_record.alist(request)

        if response.success() and response.data.total > 0:
            return True
        return False
    except Exception as e:
        print(f"Error checking duplicate: {e}")
        return True

async def add_records_to_bitable(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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

async def update_records_in_bitable(updates: List[Dict[str, Any]]):
    """
    Updates records in the Bitable. Each update needs a record_id.
    """
    client = get_lark_client()
    request_records = [
        UpdateAppTableRecordRequest.builder().record_id(upd.pop('record_id')).fields(upd).build() for upd in updates
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

async def get_pending_tasks_from_bitable(count: int) -> List[Dict[str, Any]]:
    """
    Gets a specified number of tasks with 'PENDING' status.
    """
    client = get_lark_client()
    request = ListAppTableRecordRequest.builder() \
        .app_token(settings.FEISHU_BITABLE_APP_TOKEN) \
        .table_id(settings.FEISHU_BITABLE_TABLE_ID) \
        .filter('CurrentValue.[Status] = "PENDING"') \
        .page_size(count) \
        .build()
        
    response = await client.bitable.v1.app_table_record.alist(request)
    if not response.success():
        raise Exception(f"Failed to get pending tasks: {response.msg}")
    
    return [{"record_id": r.record_id, **r.fields} for r in response.data.items]

# --- Celery Publisher & Notification Operations ---

def publish_to_celery(tasks: List[Dict[str, Any]], priority: int):
    """
    Publishes tasks directly to Celery.
    """
    # Wrap 10 tasks into one message as per original requirement
    chunked_tasks = [tasks[i:i + 10] for i in range(0, len(tasks), 10)]
    
    for chunk in chunked_tasks:
        celery_app.send_task(
            name=settings.CELERY_TASK_NAME,
            args=[chunk],
            queue=settings.CELERY_QUEUE,
            priority=priority
        )
    print(f"Sent {len(tasks)} tasks to Celery queue '{settings.CELERY_QUEUE}' with priority {priority}.")

async def send_feishu_notification(message: str):
    """
    Sends a notification to a Feishu group using a robot webhook.
    """
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