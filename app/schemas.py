from typing import List, Dict, Any, TypedDict
from enum import Enum

class StatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class TaskRecord(TypedDict):
    id: str
    status: str # Supabase client prefers string for enum
    payload: str

class TaskUpdate(TypedDict):
    record_id: str
    fields: Dict[str, Any]

class StatusUpdate(TypedDict):
    record_id: str
    status: str
