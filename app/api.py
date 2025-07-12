import hashlib
import json
from loguru import logger
from fastapi import APIRouter, HTTPException, Body, Depends, Header
from typing import List, Dict, Any, TypedDict, Union

# --- Type Definitions ---

class StatusUpdate(TypedDict):
    record_id: str
    status: str

from . import services, state, archiver
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
    Receives data, efficiently checks for duplicates against the archive, 
    and saves only new tasks to the database.
    """
    if not data:
        return {"message": "Empty input.", "tasks_added": 0}

    # 1. Create potential task records with IDs
    potential_records = services.create_task_records(data, StatusEnum.PENDING)
    potential_ids = [rec['id'] for rec in potential_records]

    # 2. Bulk check for duplicates against Momento
    existing_mask = await archiver.check_if_ids_exist(potential_ids)

    # 3. Filter out tasks that already exist
    new_records = [rec for rec, exists in zip(potential_records, existing_mask) if not exists]
    
    if not new_records:
        return {
            "message": "All tasks are duplicates.",
            "tasks_added": 0,
            "tasks_duplicated": len(potential_records)
        }

    # 4. Ingest only the new tasks into Supabase
    try:
        added_tasks = await services.add_tasks(new_records)
        return {
            "message": "Data ingestion complete.",
            "tasks_added": len(added_tasks),
            "tasks_duplicated": len(potential_records) - len(added_tasks)
        }
    except Exception as e:
        logger.error(f"Error during data ingestion: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during data ingestion.")

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
        
        # Then, create and save records to the database
        records_to_add = services.create_task_records(tasks_list, StatusEnum.PROCESSING)
        await services.add_tasks(records_to_add)
        
        return {"message": "High-priority tasks published and saved successfully."}
    except Exception as e:
        logger.error(f"Error in priority queue task: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the priority task.")

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
        await services.update_tasks(bitable_updates)
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
