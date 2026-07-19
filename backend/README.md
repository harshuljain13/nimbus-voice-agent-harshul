# Nimbus Voice Agent — backend

FastAPI backend for the Nimbus voice agent. One process; REST + (later) a WebSocket
voice loop. Every stage reports latency.

## Run locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example ../.env      # then fill in OPENAI/GEMINI/ELEVENLABS keys
uvicorn app.main:app --reload --port 8100
```

Keys are read from `.env` (repo root or `backend/.env`) or sent per-request from the
frontend via `X-OpenAI-Key` / `X-Gemini-Key` / `X-ElevenLabs-Key` headers.

## Endpoints (Phase 0)

- `GET /health` — liveness + provider key availability + demo latency trace
- `GET /config/providers` — provider availability + LLM model registry + embedding profile

## Layout

```
app/
  main.py       FastAPI app (REST; WS added later)
  config.py     provider keys + model registry + EMBEDDING_PROFILE
  latency.py    per-stage latency trace + timers
  adapters.py   uniform ASR/LLM/TTS adapter interface
  asr/ llm/ tts/  provider adapters (implemented per phase)
```
