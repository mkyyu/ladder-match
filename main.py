from fastapi import FastAPI
from match_router import router as match_router

app = FastAPI()
app.include_router(match_router)
