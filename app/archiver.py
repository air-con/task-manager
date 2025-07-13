from loguru import logger
from datetime import datetime, timedelta
from momento import CacheClient, Configurations, CredentialProvider
from momento.responses import CacheSetAddElements, CacheSetContainsElements

from . import services, clients

CACHE_NAME = "task-archive"
SET_NAME = "processed-task-ids"

# --- Momento Client Initialization ---

# The client is now initialized in app/main.py and shared via app/clients.py

# --- Archiver Logic ---

async def archive_completed_tasks():
    """
    Fetches completed tasks from Supabase, archives their IDs to Momento,
    and then deletes the archived tasks from Supabase.
    """
    logger.info("Starting task archival process...")
    
    try:
        # 1. Fetch completed tasks from Supabase
        # We fetch tasks older than 1 day to avoid race conditions with ongoing updates.
        yesterday = datetime.now() - timedelta(days=1)
        completed_tasks = await services.get_completed_tasks_before(yesterday)

        if not completed_tasks:
            logger.info("No tasks to archive. Process finished.")
            return

        task_ids = [task['id'] for task in completed_tasks]
        logger.info(f"Found {len(task_ids)} tasks to archive.")

        # 2. Archive IDs to Momento
        add_response = await clients.momento_client.set_add_elements(CACHE_NAME, SET_NAME, task_ids)
        if isinstance(add_response, CacheSetAddElements.Success):
            logger.info(f"Successfully archived {len(task_ids)} IDs to Momento.")
        else:
            logger.error(f"Failed to archive IDs to Momento: {add_response}")
            return # Do not proceed with deletion if archival fails

        # 3. Delete archived tasks from Supabase
        delete_response = await services.delete_tasks(task_ids)
        logger.info(f"Successfully deleted {len(delete_response)} tasks from Supabase.")

        logger.info("Task archival process finished successfully.")

    except Exception as e:
        logger.error(f"An error occurred during the task archival process: {e}")

# --- Helper services needed for archiver ---

async def check_if_ids_exist(ids: List[str]) -> List[bool]:
    """
    Checks a list of IDs against the Momento cache to see if they already exist.
    """
    if not ids:
        return []
    
    try:
        response = await clients.momento_client.set_contains_elements(CACHE_NAME, SET_NAME, ids)
        if isinstance(response, CacheSetContainsElements.Success):
            return response.contains_elements
        else:
            logger.error(f"Failed to check IDs in Momento: {response}")
            # In case of failure, assume all might be duplicates to be safe.
            return [True] * len(ids)
    except Exception as e:
        logger.error(f"An error occurred while checking IDs in Momento: {e}")
        return [True] * len(ids)
