from fastapi import APIRouter

from app.api.v1 import projects, tasks, users
from app.api.v1.auth import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users.router)
api_router.include_router(tasks.router)
api_router.include_router(projects.router)
