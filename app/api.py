from loguru import logger
from fastapi import APIRouter, HTTPException, Body, Depends, Header
from typing import List, Dict, Any, TypedDict, Union

# --- Type Definitions ---

class StatusUpdate(TypedDict):
    record_id: str
    status: str

from . import services, state
from .services import StatusEnum
from .config import settings

router = APIRouter()

# --- Security --- 

import secrets

async def api_key_auth(x_api_key: str = Header(None)):
    if not settings.API_KEY_HASH:
        # If no key is set in the backend, disable auth.
        return

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    # Hash the provided key and compare with the stored hash in a secure way.
    provided_key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    
    if not secrets.compare_digest(provided_key_hash, settings.API_KEY_HASH):
        raise HTTPException(status_code=401, detail="Invalid API Key")

# --- API Endpoints ---

@router.post("/tasks/ingest")
async def ingest_data(data: List[Dict[str, Any]] = Body(...)):
    """
    Receives data, checks for duplicates, and saves it to the Bitable with PENDING status.
    The duplication check is based on a hash of the item's content.
    """
    records_to_add = []
    for item in data:
        # Create a canonical JSON string for both hashing and storing.
        # sort_keys ensures consistent hashing.
        # ensure_ascii=False preserves non-ASCII characters.
        payload_json = json.dumps(item, sort_keys=True, ensure_ascii=False)
        identifier = hashlib.md5(payload_json.encode()).hexdigest()
        records_to_add.append({
            "id": identifier,
            "status": StatusEnum.PENDING,
            "payload": payload_json
        })

    if not records_to_add:
        return {"message": "Empty input.", "tasks_added": 0}

    try:
        # Optimistic batch insert
        added_tasks = await services.add_records_to_bitable(records_to_add)
        return {
            "message": "Data ingested successfully.",
            "tasks_added": len(added_tasks),
            "tasks_duplicated": len(records_to_add) - len(added_tasks)
        }
    except Exception as e:
        # If batch fails due to duplicates, fallback to individual inserts
        if "duplicate" in str(e).lower():
            logger.warning("Batch insert failed due to duplicates, falling back to individual inserts.")
            successful_inserts = 0
            duplicate_inserts = 0
            for record in records_to_add:
                if await services.add_single_record(record):
                    successful_inserts += 1
                else:
                    duplicate_inserts += 1
            return {
                "message": "Data ingested with some duplicates.",
                "tasks_added": successful_inserts,
                "tasks_duplicated": duplicate_inserts
            }
        else:
            # For other errors, re-raise
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/priority-queue")
async def priority_queue_task(tasks: Union[Dict[str, Any], List[Dict[str, Any]]] = Body(...), priority: int = 5):
    """
    Receives a task or list of tasks, publishes it directly to the MQ with high priority,
    and saves it to the Bitable with PROCESSING status.
    """
    try:
        # Standardize input to always be a list for consistent processing
        tasks_list = tasks if isinstance(tasks, list) else [tasks]

        # Publish to Celery first with the specified priority
        services.publish_to_celery(tasks_list, priority=priority)
        
        # Then, add to Bitable with PROCESSING status
        records_to_add = []
        for task in tasks_list:
            payload_json = json.dumps(task, sort_keys=True, ensure_ascii=False)
            identifier = hashlib.md5(payload_json.encode()).hexdigest()
            records_to_add.append({
                "id": identifier,
                "status": StatusEnum.PROCESSING,
                "payload": payload_json
            })
            
        await services.add_records_to_bitable(records_to_add)
        
        return {"message": "High-priority tasks published and saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/update-status")
async def update_task_status(updates: List[StatusUpdate] = Body(...)):
    """
    Updates the status of multiple tasks based on their record_ids.
    The body should be a list of objects, e.g.: 
    [{"record_id": "rec_id1", "status": "SUCCESS"},
     {"record_id": "rec_id2", "status": "FAILED"}]
    """
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided.")

    bitable_updates = []
    for update in updates:
        record_id = update.get("record_id")
        status = update.get("status")
        if not record_id or not status:
            raise HTTPException(status_code=400, detail="Each update must have a record_id and a status.")
        
        if status not in [s.value for s in StatusEnum]:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}. Must be one of {list(StatusEnum)}")

        bitable_updates.append({
            "record_id": record_id,
            "fields": {"status": status}
        })

    try:
        await services.update_records_in_bitable(bitable_updates)
        return {"message": "Task statuses updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/notifications/status")
async def get_notification_status():
    """
    Returns the current status of the notification switch.
    """
    return {"notifications_enabled": state.NOTIFICATIONS_ENABLED}

@router.post("/notifications/toggle")
async def toggle_notifications(enabled: bool = Body(..., embed=True)):
    """
    Enables or disables notifications.
    """
    state.NOTIFICATIONS_ENABLED = enabled
    return {"message": f"Notifications have been {'enabled' if enabled else 'disabled'}.", "notifications_enabled": state.NOTIFICATIONS_ENABLED}
