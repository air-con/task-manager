from loguru import logger
import json
import hashlib
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *

from . import services
from .config import get_settings
from .schemas import StatusEnum

async def sync_feishu_task_results():
    """
    Fetches task results from a Feishu Bitable, updates Supabase accordingly,
    and then deletes the processed records from Feishu.
    """
    logger.info("Starting Feishu task result synchronization...")
    settings = get_settings()
    
    # 1. Initialize Feishu Client
    try:
        client = lark.Client.builder() \
            .app_id(settings.FEISHU_APP_ID) \
            .app_secret(settings.FEISHU_APP_SECRET) \
            .build()
    except Exception as e:
        logger.error(f"Failed to initialize Feishu client: {e}")
        return

    # 2. Fetch all records from the Feishu table
    try:
        request = ListAppTableRecordRequest.builder() \
            .app_token(settings.FEISHU_BITABLE_APP_TOKEN) \
            .table_id(settings.FEISHU_BITABLE_TABLE_ID) \
            .build()
        response = await client.bitable.v1.app_table_record.alist(request)
        if not response.success():
            logger.error(f"Failed to fetch records from Feishu: {response.msg}")
            return
        feishu_records = response.data.items
    except Exception as e:
        logger.error(f"An error occurred while fetching from Feishu: {e}")
        return

    if not feishu_records:
        logger.info("No records found in Feishu table to sync.")
        return

    logger.info(f"Found {len(feishu_records)} records in Feishu to process.")

    # 3. Process records and prepare updates
    supabase_updates = []
    record_ids_to_delete_from_feishu = []

    for record in feishu_records:
        record_id_feishu = record.record_id
        fields = record.fields
        record_ids_to_delete_from_feishu.append(record_id_feishu)

        try:
            input_str = fields.get("input", "{}")
            input_data = json.loads(input_str)
            canonical_json = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
            task_id_supabase = hashlib.md5(canonical_json.encode()).hexdigest()

            state = fields.get("state")
            success = str(fields.get("success", 'False')).lower() == 'true'

            new_status = None
            if state == 'SUCCESS' and success:
                new_status = StatusEnum.SUCCESS
            elif state == 'SUCCESS' and not success:
                new_status = StatusEnum.FAILED
            else: # state is not SUCCESS
                new_status = StatusEnum.PENDING

            supabase_updates.append({
                "record_id": task_id_supabase,
                "fields": {"status": new_status.value}
            })

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping malformed Feishu record (ID: {record_id_feishu}): {e}")
            continue

    # 4. Batch update Supabase
    if supabase_updates:
        try:
            await services.update_tasks(supabase_updates)
            logger.info(f"Successfully sent {len(supabase_updates)} status updates to Supabase.")
        except Exception as e:
            logger.error(f"Failed to update Supabase, will not delete records from Feishu. Error: {e}")
            return # IMPORTANT: Do not delete from Feishu if Supabase update fails

    # 5. Batch delete records from Feishu
    if record_ids_to_delete_from_feishu:
        try:
            delete_request = BatchDeleteAppTableRecordRequest.builder() \
                .app_token(settings.FEISHU_BITABLE_APP_TOKEN) \
                .table_id(settings.FEISHU_BITABLE_TABLE_ID) \
                .request_body(BatchDeleteAppTableRecordRequestBody.builder() \
                    .records(record_ids_to_delete_from_feishu) \
                    .build()) \
                .build()
            delete_response = await client.bitable.v1.app_table_record.abatch_delete(delete_request)
            if not delete_response.success():
                logger.error(f"Failed to delete records from Feishu: {delete_response.msg}")
            else:
                logger.info(f"Successfully deleted {len(record_ids_to_delete_from_feishu)} records from Feishu.")
        except Exception as e:
            logger.error(f"An error occurred while deleting records from Feishu: {e}")

    logger.info("Feishu task result synchronization finished.")