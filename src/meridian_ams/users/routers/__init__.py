from fastapi import APIRouter

from meridian_ams.users.routers.system_admin import router as system_admin_router

router = APIRouter()

router.include_router(system_admin_router)
