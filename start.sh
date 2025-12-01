#!/bin/bash

# Start FastAPI backend in background
uvicorn apicodenew2:app --host 0.0.0.0 --port 8000 &

# Wait for backend to start
sleep 15

# Start Streamlit frontend
streamlit run frontbe4.py --server.port 8501 --server.address 0.0.0.0
