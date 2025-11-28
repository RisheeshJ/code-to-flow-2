## 🚀 Overview

Code2Flow converts raw source code into clean, readable **Mermaid flowcharts**, combining:

- **Tree-sitter** (static analysis)
- **Groq LLM** (flowchart generation)
- **FastAPI** backend
- **Streamlit** frontend

Users can paste or upload code → backend processes it → frontend displays the final flowchart.

---

## 📂 Project Structure

```plaintext
code-to-flow-2/
│
├── thisworks.py       # Backend logic (Tree-sitter + LLM + chunking + Mermaid)
├── apicodenew2.py     # FastAPI API server
├── frontbe4.py        # Streamlit frontend UI
└── README.md          # Documentation

🧠 File Responsibilities
1️⃣ thisworks.py — Backend Engine

Core analysis + flowchart generation.
Contains:

Language detection

Tree-sitter parsing

Function extraction

Smart chunking

LLM prompts

Mermaid flowchart creation

SVG rendering

2️⃣ apicodenew2.py — FastAPI API Layer

Implements backend endpoints:

POST /submit-code

POST /set-language/{session_id}

POST /generate-flowchart/{session_id}

POST /generate (all-in-one)

GET /logs

GET /current

This file connects the frontend to the backend engine.

3️⃣ frontbe4.py — Streamlit Frontend UI

Interactive UI where users can:

Paste or upload code

Select language

Generate flowcharts

View Mermaid code

View SVG output

View logs

Communicates with FastAPI using HTTP requests.

⚙️ How to Run the Project
1. Install dependencies
pip install fastapi uvicorn streamlit requests tree_sitter python-dotenv langchain-groq

2. Start Backend API (FastAPI)
python apicodenew2.py

3. Start Frontend (Streamlit)
streamlit run frontbe4.py

✨ Features

Automatic language detection

Multi-language support (Python / JS / C)

Tree-sitter function extraction

LLM-powered flowcharts

Combined multi-function diagrams

SVG + Mermaid output

Saved logs

Clean UI
