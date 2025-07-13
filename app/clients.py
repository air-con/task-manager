from typing import Optional
import httpx
from momento import CacheClient

# These clients will be initialized during the application startup
httpx_client: Optional[httpx.AsyncClient] = None
momento_client: Optional[CacheClient] = None
