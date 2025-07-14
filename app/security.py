import secrets
import hashlib
from fastapi import Header, HTTPException

from .config import get_settings

async def api_key_auth(x_api_key: str = Header(None)):
    settings = get_settings()
    if not settings.API_KEY_HASH:
        # If no key is set in the backend, authentication is disabled.
        return

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    # Hash the provided key and compare with the stored hash in a secure way.
    provided_key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    
    if not secrets.compare_digest(provided_key_hash, settings.API_KEY_HASH):
        raise HTTPException(status_code=401, detail="Invalid API Key")
