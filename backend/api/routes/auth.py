
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.security.device_auth import get_device_token


router = APIRouter(prefix="/api/auth", tags=["Device auth"])


class PairRequest(BaseModel):
    token: str


@router.post("/pair")
async def pair(request: PairRequest):
    # Token check itself happens in DeviceAuthMiddleware; reaching this
    # handler means the presented token was already valid.
    get_device_token()

    if request.token.strip() != get_device_token():
        raise HTTPException(
            status_code=401,
            detail="Invalid device token.",
        )

    return {"paired": True}


@router.get("/status")
async def status():
    return {"paired": True}
