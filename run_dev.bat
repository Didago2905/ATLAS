start cmd /k "uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
start cmd /k "cd frontend && npm run dev -- --host"