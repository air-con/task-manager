import hashlib
from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any

from . import services
from .config import settings

router = APIRouter()

# --- API Endpoints ---

@router.post("/tasks/ingest")
async def ingest_data(data: List[Dict[str, Any]] = Body(...)):
    """
    Receives data, checks for duplicates, and saves it to the Bitable with PENDING status.
    The duplication check is based on a hash of the item's content.
    """
    new_records = []
    for item in data:
        # Create a unique identifier for the task to check for duplicates
        identifier = hashlib.sha256(str(item).encode()).hexdigest()
        
        is_duplicate = await services.check_duplicate(identifier)
        if not is_duplicate:
            new_records.append({
                **item,
                "Identifier": identifier,
                "Status": "PENDING"
            })

    if not new_records:
        return {"message": "Data already exists or empty input.", "tasks_added": 0}

    try:
        added_tasks = await services.add_records_to_bitable(new_records)
        return {"message": "Data ingested successfully.", "tasks_added": len(added_tasks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/priority-queue")
async def priority_queue_task(tasks: List[Dict[str, Any]] = Body(...)):
    """
    Receives a task or list of tasks, publishes it directly to the MQ with high priority,
    and saves it to the Bitable with PROCESSING status.
    """
    try:
        # Publish to Celery first with high priority
        services.publish_to_celery(tasks, priority=settings.CELERY_HIGH_PRIORITY)
        
        # Then, add to Bitable with PROCESSING status
        records_to_add = []
        for task in tasks:
            identifier = hashlib.sha256(str(task).encode()).hexdigest()
            records_to_add.append({
                **task,
                "Identifier": identifier,
                "Status": "PROCESSING"
            })
            
        await services.add_records_to_bitable(records_to_add)
        
        return {"message": "High-priority tasks published and saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/update-status")
async def update_task_status(updates: Dict[str, List[str]] = Body(...)):
    """
    Updates the status of multiple tasks based on their record_ids.
    The body should be like: {"SUCCESS": ["rec_id1", "rec_id2"], "FAILED": ["rec_id3"]}
    """
    bitable_updates = []
    for status, record_ids in updates.items():
        if status not in ["SUCCESS", "FAILED", "PENDING"]:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        for record_id in record_ids:
            bitable_updates.append({
                "record_id": record_id,
                "fields": {"Status": status}
            })
            
    if not bitable_updates:
        raise HTTPException(status_code=400, detail="No updates provided.")

    try:
        await services.update_records_in_bitable(bitable_updates)
        return {"message": "Task statuses updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
