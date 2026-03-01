from fastapi.security import APIKeyHeader
from fastapi import Depends, HTTPException, Security
from app.config import get_settings, Settings

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(key: str = Security(api_key_header), settings: Settings = Depends(get_settings)) -> None:
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")