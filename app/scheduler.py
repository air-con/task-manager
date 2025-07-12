from loguru import logger

from . import services
from .config import settings

TASK_POOL_THRESHOLD = 3000
TASK_REPLENISH_COUNT = 5000 # Replenish up to 5000, but the logic will fetch 500 at a time.

async def check_and_replenish_tasks():
    """
    Checks the number of tasks in the MQ (simulated) and replenishes them from the database if below a threshold.
    """
    # In a real scenario, you would query the MQ to get the current queue size.
    # Here, we'll simulate this by checking the number of PENDING tasks in Bitable
    # as a proxy for the available task pool.
    
    try:
        pending_tasks = await services.get_pending_tasks_from_bitable(TASK_POOL_THRESHOLD + 1)
        current_task_count = len(pending_tasks)
        
        logger.info(f"Current pending tasks: {current_task_count}. Threshold: {TASK_POOL_THRESHOLD}")

        if current_task_count < TASK_POOL_THRESHOLD:
            tasks_to_fetch = TASK_REPLENISH_COUNT - current_task_count
            # Fetch in batches of 500 as per requirement
            tasks_to_fetch = min(tasks_to_fetch, 500)
            
            await services.send_feishu_notification(
                f"Task pool is low ({current_task_count}). Replenishing {tasks_to_fetch} tasks."
            )
            
            # Get tasks from Bitable that are in PENDING state
            new_tasks = await services.get_pending_tasks_from_bitable(tasks_to_fetch)
            
            if not new_tasks:
                logger.info("No pending tasks available to replenish.")
                return

            # Chunk tasks into groups of 10 before publishing
            chunked_tasks = [new_tasks[i:i + 10] for i in range(0, len(new_tasks), 10)]
            for chunk in chunked_tasks:
                services.publish_to_celery(
                    [task['fields'] for task in chunk]
                )
            
            # Update their status to PROCESSING
            updates = [
                {"record_id": task['record_id'], "fields": {"Status": "PROCESSING"}}
                for task in new_tasks
            ]
            await services.update_records_in_bitable(updates)
            
            logger.info(f"Successfully replenished {len(new_tasks)} tasks.")

    except Exception as e:
        logger.error(f"Error during scheduled task check: {e}")
        await services.send_feishu_notification(f"ERROR: Task replenishment failed: {e}")
