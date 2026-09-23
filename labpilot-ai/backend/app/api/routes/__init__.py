from fastapi import APIRouter

from app.api.routes import auth, copilot, copilot_chat, experiments, learning, students, submissions, system, teacher, users, viva, whatif

api_router = APIRouter()
for module in (auth, users, students, experiments, submissions, copilot, copilot_chat, viva, whatif, teacher, system):
    api_router.include_router(module.router)
for router in (learning.mistakes_router, learning.skills_router, learning.reco_router):
    api_router.include_router(router)
