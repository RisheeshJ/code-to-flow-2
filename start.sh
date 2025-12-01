#!/bin/bash

# Start FastAPI backend on internal port (not exposed publicly)
uvicorn apicodenew2:app --host 127.0.0.1 --port 8000 &

# Wait for backend to start
sleep 15

# Start Streamlit frontend on port from environment variable (Render will set this)
streamlit run frontbe4.py --server.port ${PORT:-8501} --server.address 0.0.0.0
