from loguru import logger

from . import services
from config import get_settings

# If the number of pending tasks drops below 60% of the replenish count, trigger replenishment.
TASK_POOL_THRESHOLD_RATIO = 0.6

async def check_and_replenish_tasks():
    """
    Checks the number of tasks in the MQ and replenishes them from the database if below a threshold.
    """
    try:
        task_pool_threshold = int(get_settings().SCHEDULER_TASK_REPLENISH_COUNT * TASK_POOL_THRESHOLD_RATIO)
        
        # Get the current queue size directly from RabbitMQ
        current_task_count = services.get_mq_queue_size(get_settings().CELERY_QUEUE)

        if current_task_count == -1:
            logger.error("Could not get task count from MQ. Skipping replenishment cycle.")
            return

        logger.info(f"Current tasks in MQ: {current_task_count}. Threshold: {task_pool_threshold}")

        if current_task_count < task_pool_threshold:
            tasks_to_fetch = get_settings().SCHEDULER_TASK_REPLENISH_COUNT - current_task_count
            # Fetch in batches of 500 as per requirement
            tasks_to_fetch = min(tasks_to_fetch, 500)
            
            logger.info(f"Task pool is low ({current_task_count}). Replenishing {tasks_to_fetch} tasks.")
            
            # Get tasks from Supabase that are in PENDING state
            new_tasks = await services.get_pending_tasks(tasks_to_fetch)
            
            if not new_tasks:
                logger.info("No pending tasks available to replenish.")
                return

            # Publish tasks based on the configured batch size
            batch_size = get_settings().SCHEDULER_BATCH_SIZE
            if batch_size > 1:
                logger.info(f"Publishing tasks in multi-mode with batch size {batch_size}.")
                chunked_tasks = [new_tasks[i:i + batch_size] for i in range(0, len(new_tasks), batch_size)]
                for chunk in chunked_tasks:
                    services.publish_to_celery([task['payload'] for task in chunk])
            else: # single mode
                logger.info("Publishing tasks in single-mode.")
                for task in new_tasks:
                    services.publish_to_celery(task['payload'])
            
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
