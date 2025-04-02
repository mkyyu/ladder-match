from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List, Any
import uuid
import time

router = APIRouter()

active_matches: Dict[str, Dict[str, Any]] = {}

def generate_match_id():
    return str(uuid.uuid4())[:8]

@router.post("/create_match")
async def create_match(payload: Dict[str, Any]):
    match_id = generate_match_id()
    questions = payload.get("questions")
    subject = payload.get("subject")
    year_level = payload.get("year_level")
    if not questions or not subject or not year_level:
        raise HTTPException(status_code=400, detail="Missing fields")

    active_matches[match_id] = {
        "players": {},
        "questions": questions,
        "current_question": 0,
        "created_at": time.time()
    }
    return {"match_id": match_id}

@router.get("/match_lobby")
async def match_lobby():
    return [{"match_id": mid, "players": list(data["players"].keys())} for mid, data in active_matches.items()]

@router.websocket("/ws/match/{match_id}/{username}")
async def match_socket(ws: WebSocket, match_id: str, username: str):
    await ws.accept()
    if match_id not in active_matches:
        await ws.close()
        return
    active_matches[match_id]["players"][username] = {"score": 0}
    await ws.send_json({"msg": f"{username} joined match {match_id}"})