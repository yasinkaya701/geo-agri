#!/bin/bash

# Start FastAPI backend in the background on port 8000
python -m uvicorn src.main_backend:app --host 0.0.0.0 --port 8000 > /tmp/fastapi.log 2>&1 &

# Start Celery worker in the background
python -m celery -A src.tasks.celery_app worker --loglevel=info > /tmp/celery.log 2>&1 &

# Start Streamlit on the port provided by Railway ($PORT)
streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0
