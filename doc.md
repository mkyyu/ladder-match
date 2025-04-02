# yueming Services: LADDER Real-Time Matchmaking Backend

A lightweight FastAPI-based backend that enables real-time MCQ competitions for students. This supports matchmaking (auto/manual), WebSocket-based gameplay, and in-memory session management.

---

## Features

- Teacher-created or auto-matched games
- Multi-player support with real-time updates
- Join via matchmaking queue or direct code
- Player score tracking with bonus streaks
- Per-question leaderboards and game history
- Spectator mode with real-time view
- Timeout and match expiration
- Streak bonuses and anti-cheat timer
- Custom subject, year level, and number of questions

---

## Installation (for mk reference)

### 1. Clone the repository

```bash
git clone https://github.com/mkyyu/ladder-match
cd ladder-match
```

### 2. Set up Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the server

```bash
uvicorn main:app --host 127.0.0.1 --port 3000
```

---

## Production deployment using Nginx on Ubuntu-based systems
### Step 1: Create Systemd Service

`/etc/systemd/system/ladder-match.service`

```ini
[Unit]
Description=Ladder MCQ Match FastAPI Server
After=network.target

[Service]
User=root
WorkingDirectory=/root/ladder-match
ExecStart=/root/ladder-match/venv/bin/uvicorn main:app --host 127.0.0.1 --port 3000
Restart=always

[Install]
WantedBy=multi-user.target
```

### Step 2: Reload and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable ladder-match
sudo systemctl start ladder-match
sudo systemctl status ladder-match
```

### Step 3: Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl;
    server_name ladder-rtmatch.services.yueming.org;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    ssl_certificate /etc/letsencrypt/live/yourdomain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain/privkey.pem;
}
```

---

## API Endpoints

### `POST /create_match`

Create a custom match.

```json
{
  "questions": [{ "question": "...", "options": ["A","B"], "answer": "A", "marks": 1, "time_limit": 30 }],
  "subject": "Biology",
  "year_level": "Year 10",
  "teacher_created": true
}
```

Returns:

```json
{ "match_id": "abc123" }
```

---

### `POST /join_match`

Join a match with `match_id`.

```json
{ "match_id": "abc123", "username": "alice" }
```

Returns:

```json
{ "message": "Joined match successfully", "subject": "...", "year_level": "...", "teacher_created": true }
```

---

### `POST /queue_match`

Auto-matchmaking queue.

```json
{
  "username": "alice",
  "subject": "Chemistry",
  "year_level": "Year 9"
}
```

Returns:

```json
{ "match_id": "xyz789", "message": "Auto-matched" }
```

---

### `GET /match_lobby`

List active matches.

```json
[
  {
    "match_id": "abc123",
    "subject": "Math",
    "year_level": "Year 8",
    "players": ["alice", "bob"],
    "spectators": 1
  }
]
```

---

### `GET /ping`

Health check.

```json
{ "status": "ok" }
```

---

## WebSocket Endpoint

`/ws/match/{match_id}/{username}`

### Connection message:

```json
{ "type": "connected", "user": "alice", "role": "player" }
```

---

### Supported WebSocket Actions:

| Action | Description |
|--------|-------------|
| `start_match` | Starts first question |
| `submit_answer` | Submit answer with optional multiplier |
| `next_question` | Move to next question |
| `answer_result` | Returns correctness, score, and streak |
| `leaderboard` | Live leaderboard refresh |
| `end` | End of match summary |

Great question! Here's a breakdown of the expected **WebSocket (`/ws/match/{match_id}/{username}`)** message flows and outputs from the Ladder Match server:

---

## On Successful Connection

```json
{
  "type": "connected",
  "user": "alice",
  "role": "player"  // or "spectator"
}
```

---

## Real-Time WebSocket Outputs

### 1. **User Joined Notification**

Sent to existing players when a new player joins:

```json
{
  "type": "user_joined",
  "user": "bob"
}
```

---

### 2. **Start Match (First Question Broadcast)**

Sent when a player sends `{ action: "start_match" }`:

```json
{
  "type": "question",
  "data": {
    "question": "What is 2+2?",
    "options": ["1", "2", "3", "4"],
    "answer": "4",
    "marks": 1,
    "time_limit": 30
  },
  "number": 1,
  "time_limit": 30
}
```

---

### 3. **Answer Result**

After submitting an answer:

```json
{
  "type": "answer_result",
  "correct": true,
  "score": 2,
  "streak": 2,
  "answer_log": {
    "alice": {
      "answer": "4",
      "correct": true
    }
  }
}
```

---

### 4. **Live Leaderboard Refresh**

Sent to everyone after an answer:

```json
{
  "type": "leaderboard",
  "leaderboard": [
    { "user": "alice", "score": 3 },
    { "user": "bob", "score": 2 }
  ]
}
```

---

### 5. **Next Question**

Sent when someone triggers `{ action: "next_question" }`:

```json
{
  "type": "question",
  "data": {
    "question": "What is H2O?",
    "options": ["Water", "Oxygen", "Hydrogen", "Helium"],
    "answer": "Water",
    "marks": 1,
    "time_limit": 30
  },
  "number": 2,
  "time_limit": 30
}
```

---

### 6. **Match Ended**

Sent when all questions are complete:

```json
{
  "type": "end",
  "scores": {
    "alice": 4,
    "bob": 2
  },
  "leaderboard": [
    { "user": "alice", "score": 4 },
    { "user": "bob", "score": 2 }
  ]
}
```

---

### 7. **Anti-Cheat / Throttling Error**

If a user spams answers:

```json
{
  "type": "error",
  "message": "Answer too fast. Cheating suspected."
}
```

---

## FlutterFlow

You can use custom actions for REST + WebSocket:

### REST Call Example (create match)

```dart
await http.post(
  Uri.parse('https://ladder-rtmatch.services.yueming.org/create_match'),
  headers: {'Content-Type': 'application/json'},
  body: json.encode({...})
);
```

### WebSocket Example

```dart
final socket = IOWebSocketChannel.connect(
  'wss://ladder-rtmatch.services.yueming.org/ws/match/abc123/alice'
);
socket.stream.listen((data) {
  final message = jsonDecode(data);
  // handle message
});
```