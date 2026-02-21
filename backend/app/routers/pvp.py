# app/routers/pvp.py

from fastapi import APIRouter

from app.routers.pvp_common import router as pvp_common_router
from app.routers.pvp_live import router as pvp_live_router
from app.routers.pvp_challenge import router as pvp_challenge_router

router = APIRouter()
router.include_router(pvp_common_router)
router.include_router(pvp_live_router)
router.include_router(pvp_challenge_router)









