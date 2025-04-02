from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List, Any
import uuid
import time

router = APIRouter()

# In-memory match state
active_matches: Dict[str, Dict[str, Any]] = {}
matchmaking_queue: List[Dict[str, str]] = []

MATCH_TIMEOUT = 600  # Match expires after 10 mins
STREAK_BONUS = 1      # Bonus score for streaks
ANSWER_COOLDOWN = 1.0 # Prevent rapid repeated answering

def generate_match_id():
    return str(uuid.uuid4())[:8]

@router.post("/create_match")
async def create_match(payload: Dict[str, Any]):
    match_id = generate_match_id()
    questions = payload.get("questions")
    subject = payload.get("subject")
    year_level = payload.get("year_level")
    teacher_created = payload.get("teacher_created", False)

    if not questions or not subject or not year_level:
        raise HTTPException(status_code=400, detail="Missing required fields")

    active_matches[match_id] = {
        "players": {},
        "spectators": [],
        "questions": questions,
        "current_question": 0,
        "answers_log": {},
        "subject": subject,
        "year_level": year_level,
        "teacher_created": teacher_created,
        "created_at": time.time(),
        "question_start_time": None
    }
    return {"match_id": match_id}

@router.post("/queue_match")
async def queue_match(payload: Dict[str, str]):
    matchmaking_queue.append(payload)
    for other in matchmaking_queue:
        if other == payload:
            continue
        if other["subject"] == payload["subject"] and other["year_level"] == payload["year_level"]:
            match_id = generate_match_id()
            questions = [{
                "question": "Placeholder question?",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
                "marks": 1,
                "time_limit": 30
            }]
            active_matches[match_id] = {
                "players": {
                    payload["username"]: {"score": 0, "ws": None, "last_answer_time": 0, "streak": 0},
                    other["username"]: {"score": 0, "ws": None, "last_answer_time": 0, "streak": 0}
                },
                "spectators": [],
                "questions": questions,
                "current_question": 0,
                "answers_log": {},
                "subject": payload["subject"],
                "year_level": payload["year_level"],
                "teacher_created": False,
                "created_at": time.time(),
                "question_start_time": None
            }
            matchmaking_queue.remove(payload)
            matchmaking_queue.remove(other)
            return {"match_id": match_id, "message": "Auto-matched"}

    return {"message": "Added to matchmaking queue"}

@router.post("/join_match")
async def join_match(payload: Dict[str, str]):
    match_id = payload.get("match_id")
    username = payload.get("username")
    if match_id not in active_matches:
        raise HTTPException(status_code=404, detail="Match not found")

    match = active_matches[match_id]
    match["players"][username] = {
        "score": 0,
        "ws": None,
        "last_answer_time": 0,
        "streak": 0
    }

    for user, info in match["players"].items():
        if info["ws"] and user != username:
            await info["ws"].send_json({"type": "user_joined", "user": username})

    return {
        "message": "Joined match successfully",
        "subject": match["subject"],
        "year_level": match["year_level"],
        "teacher_created": match["teacher_created"]
    }

@router.get("/match_lobby")
async def match_lobby():
    return [
        {
            "match_id": match_id,
            "subject": match["subject"],
            "year_level": match["year_level"],
            "players": list(match["players"].keys()),
            "spectators": len(match["spectators"])
        }
        for match_id, match in active_matches.items()
        if time.time() - match.get("created_at", 0) < MATCH_TIMEOUT
    ]

@router.websocket("/ws/match/{match_id}/{username}")
async def match_socket(ws: WebSocket, match_id: str, username: str):
    await ws.accept()
    if match_id not in active_matches:
        await ws.close(code=1008)
        return

    match = active_matches[match_id]

    if username in match["players"]:
        match["players"][username]["ws"] = ws
    else:
        match["spectators"].append(ws)
        await ws.send_json({"type": "connected", "user": username, "role": "spectator"})
        return

    await ws.send_json({"type": "connected", "user": username, "role": "player"})

    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "start_match":
                q = match["questions"][0]
                match["question_start_time"] = time.time()
                await broadcast(match_id, {"type": "question", "data": q, "number": 1, "time_limit": q.get("time_limit", 30)})
                match["answers_log"][0] = {}

            elif action == "submit_answer":
                answer = data.get("answer")
                multiplier = data.get("multiplier", 1)
                player = match["players"][username]
                now = time.time()

                if now - player["last_answer_time"] < ANSWER_COOLDOWN:
                    await ws.send_json({"type": "error", "message": "Answer too fast. Cheating suspected."})
                    continue
                player["last_answer_time"] = now

                q_index = match["current_question"]
                q = match["questions"][q_index]
                correct = answer == q["answer"]

                if correct:
                    player["streak"] += 1
                    bonus = STREAK_BONUS if player["streak"] >= 2 else 0
                    player["score"] += (q["marks"] * multiplier) + bonus
                else:
                    player["streak"] = 0

                match["answers_log"].setdefault(q_index, {})[username] = {
                    "answer": answer,
                    "correct": correct
                }

                await ws.send_json({
                    "type": "answer_result",
                    "correct": correct,
                    "score": player["score"],
                    "streak": player["streak"],
                    "answer_log": match["answers_log"][q_index]
                })
                await broadcast(match_id, {"type": "leaderboard", "leaderboard": get_leaderboard(match_id)})

            elif action == "next_question":
                match["current_question"] += 1
                q_index = match["current_question"]
                if q_index >= len(match["questions"]):
                    await broadcast(match_id, {
                        "type": "end",
                        "scores": get_scores(match_id),
                        "leaderboard": get_leaderboard(match_id)
                    })
                else:
                    q = match["questions"][q_index]
                    match["question_start_time"] = time.time()
                    await broadcast(match_id, {
                        "type": "question",
                        "data": q,
                        "number": q_index + 1,
                        "time_limit": q.get("time_limit", 30)
                    })
                    match["answers_log"][q_index] = {}

    except WebSocketDisconnect:
        print(f"{username} disconnected")
        match["players"][username]["ws"] = None


def get_scores(match_id: str):
    return {
        user: info["score"] for user, info in active_matches[match_id]["players"].items()
    }

def get_leaderboard(match_id: str):
    return sorted([
        {"user": user, "score": info["score"]}
        for user, info in active_matches[match_id]["players"].items()
    ], key=lambda x: x["score"], reverse=True)

async def broadcast(match_id: str, message: Dict[str, Any]):
    for player, info in active_matches[match_id]["players"].items():
        if info["ws"]:
            try:
                await info["ws"].send_json(message)
            except:
                continue
    for ws in active_matches[match_id].get("spectators", []):
        try:
            await ws.send_json(message)
        except:
            continue
