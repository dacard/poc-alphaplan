#!/bin/bash
# Sobe a API (porta 8000) e o frontend (porta 5180). Ctrl+C encerra os dois.
cd "$(dirname "$0")"
trap 'kill 0' EXIT
(cd backend && ../.venv/bin/uvicorn app.main:app --port 8000 --reload) &
(cd frontend && npx vite) &
sleep 2 && echo -e "\n  POC rodando em http://localhost:5180  (API: http://localhost:8000/docs)\n"
wait
