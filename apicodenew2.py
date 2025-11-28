# main.py - Enhanced FastAPI with separate endpoints and automatic JSON handling
from fastapi import FastAPI, HTTPException, Request, Body, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Union, Optional
import base64
import traceback
import json
import uuid
from pathlib import Path
from datetime import datetime


 

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Import your existing backend code
from thisworks import (
    detect_language,
    analyze_code_structure,
    create_chunks,
    generate_flowchart_for_chunk,
    combine_flowcharts,
    mermaid_to_svg
)

app = FastAPI(title="Code2Flow API", version="4.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# DATA MODELS
# ============================================

class CodeSubmission(BaseModel):
    code: str
    language: str = "auto"

class FlowchartResponse(BaseModel):
    success: bool
    html_svg: str
    mermaid_code: str
    status: str
    svg_url: str
    analysis: Dict[str, Any]
    session_id: str

# ============================================
# IN-MEMORY STORAGE (for session management)
# ============================================

# Store code submissions by session ID
code_storage: Dict[str, Dict[str, str]] = {}

# Global storage for current output
current_svg_url = ""
current_mermaid_code = ""

# ============================================
# UTILITY FUNCTIONS
# ============================================

def sanitize_code_to_json_string(raw_code: str) -> str:
    """
    Convert raw code into a JSON-compatible string.
    Handles newlines, quotes, and special characters.
    """
    # Replace problematic characters
    json_safe = raw_code.replace('\\', '\\\\')  # Escape backslashes first
    json_safe = json_safe.replace('"', '\\"')    # Escape double quotes
    json_safe = json_safe.replace('\n', '\\n')   # Convert newlines
    json_safe = json_safe.replace('\r', '\\r')   # Convert carriage returns
    json_safe = json_safe.replace('\t', '\\t')   # Convert tabs
    
    return json_safe

def create_json_payload(code_str: str, language: str = "auto") -> Dict[str, str]:
    """
    Create a proper JSON payload for the generate endpoint.
    """
    return {
        "code": code_str,
        "language": language
    }

def generate_session_id() -> str:
    """Generate a unique session ID"""
    return str(uuid.uuid4())

# ============================================
# MAIN ENDPOINTS
# ============================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Landing page with API documentation"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Code2Flow API v4.0</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1200px; margin: 40px auto; padding: 20px; }
            h1 { color: #2563eb; }
            .endpoint { background: #f3f4f6; padding: 15px; margin: 15px 0; border-radius: 8px; }
            .method { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
            .post { background: #10b981; color: white; }
            .get { background: #3b82f6; color: white; }
            code { background: #e5e7eb; padding: 2px 6px; border-radius: 4px; }
            .example { background: #fef3c7; padding: 15px; margin: 10px 0; border-radius: 8px; }
        </style>
    </head>
    <body>
        <h1>🚀 Code2Flow API v4.0</h1>
        <p><strong>Enhanced with separate endpoints and automatic JSON handling!</strong></p>
        
        <h2>✨ Features</h2>
        <ul>
            <li>✅ Separate endpoints for code submission and language selection</li>
            <li>✅ Automatic raw code to JSON conversion</li>
            <li>✅ Session-based workflow</li>
            <li>✅ No manual JSON formatting needed</li>
        </ul>
        
        <h2>📚 API Endpoints</h2>
        
        <div class="endpoint">
            <span class="method post">POST</span> <strong>/submit-code</strong>
            <p>Submit raw code - returns a session ID</p>
            <p>Body (form-data): <code>code</code> (text)</p>
        </div>
        
        <div class="endpoint">
            <span class="method post">POST</span> <strong>/set-language/{session_id}</strong>
            <p>Set language for a session</p>
            <p>Body: <code>{"language": "python"}</code></p>
        </div>
        
        <div class="endpoint">
            <span class="method post">POST</span> <strong>/generate-flowchart/{session_id}</strong>
            <p>Generate flowchart for a session</p>
        </div>
        
        <div class="endpoint">
            <span class="method post">POST</span> <strong>/generate</strong>
            <p>All-in-one endpoint (original method)</p>
            <p>Body: <code>{"code": "your code", "language": "python"}</code></p>
        </div>
        
        <div class="endpoint">
            <span class="method get">GET</span> <strong>/session/{session_id}</strong>
            <p>Get session details</p>
        </div>
        
        <h2>🎯 Usage Example</h2>
        <div class="example">
            <h3>Method 1: Step-by-step (Recommended)</h3>
            <ol>
                <li>POST your code to <code>/submit-code</code> → Get session_id</li>
                <li>(Optional) POST language to <code>/set-language/{session_id}</code></li>
                <li>POST to <code>/generate-flowchart/{session_id}</code> → Get flowchart</li>
            </ol>
        </div>
        
        <div class="example">
            <h3>Method 2: Direct (Original)</h3>
            <ol>
                <li>POST to <code>/generate</code> with JSON payload</li>
            </ol>
        </div>
        
        <p><a href="/docs" style="color: #2563eb; font-weight: bold;">📖 Interactive API Docs (Swagger UI) →</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "version": "4.0.0",
        "active_sessions": len(code_storage)
    }

# ============================================
# NEW SEPARATE ENDPOINTS
# ============================================

@app.post("/submit-code")
async def submit_code(code: str = Form(...)):
    """
    Step 1: Submit raw code
    Returns a session ID for subsequent operations
    """
    try:
        if not code or not code.strip():
            raise HTTPException(status_code=400, detail="Code cannot be empty")
        
        # Generate session ID
        session_id = generate_session_id()
        
        # Store code with default language
        code_storage[session_id] = {
            "code": code,
            "language": "auto"
        }
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Code submitted successfully",
            "code_length": len(code),
            "lines": len(code.splitlines())
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error submitting code: {str(e)}")

@app.post("/set-language/{session_id}")
async def set_language(
    session_id: str,
    language: str = Body(..., embed=True)
):
    """
    Step 2: Set language for a session (optional - defaults to auto)
    """
    if session_id not in code_storage:
        raise HTTPException(status_code=404, detail="Session not found")
    
    valid_languages = ["auto", "python", "javascript", "c"]
    if language not in valid_languages:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid language. Choose from: {', '.join(valid_languages)}"
        )
    
    code_storage[session_id]["language"] = language
    
    return {
        "success": True,
        "session_id": session_id,
        "language": language,
        "message": "Language set successfully"
    }

@app.post("/generate-flowchart/{session_id}", response_model=FlowchartResponse)
async def generate_flowchart_by_session(session_id: str):
    """
    Step 3: Generate flowchart for a session
    """
    global current_mermaid_code, current_svg_url
    
    if session_id not in code_storage:
        raise HTTPException(status_code=404, detail="Session not found. Submit code first.")
    
    session_data = code_storage[session_id]
    code = session_data["code"]
    language = session_data["language"]
    
    try:
        # Use the processing logic
        result = await process_code_internal(code, language)
        result["session_id"] = session_id
        
        return result
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error generating flowchart: {str(e)}"
        )

@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """
    Get session details
    """
    if session_id not in code_storage:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_data = code_storage[session_id]
    
    return {
        "session_id": session_id,
        "has_code": bool(session_data.get("code")),
        "language": session_data.get("language", "auto"),
        "code_length": len(session_data.get("code", "")),
        "lines": len(session_data.get("code", "").splitlines())
    }

# ============================================
# ORIGINAL ALL-IN-ONE ENDPOINT (kept for compatibility)
# ============================================

@app.post("/generate", response_model=FlowchartResponse)
async def generate_flowchart(
    code: str = Body(..., description="Your code"),
    language: str = Body(default="auto", description="Programming language")
):
    """
    Original all-in-one endpoint
    Generate flowchart directly from code
    """
    global current_mermaid_code, current_svg_url
    
    try:
        if not code or not code.strip():
            raise HTTPException(status_code=400, detail="Code cannot be empty")
        
        result = await process_code_internal(code, language)
        result["session_id"] = "direct"
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing code: {str(e)}"
        )

# ============================================
# INTERNAL PROCESSING FUNCTION
# ============================================

async def process_code_internal(code: str, language: str) -> Dict[str, Any]:
    """
    Internal function to process code and generate flowchart
    Used by both endpoint types
    """
    global current_mermaid_code, current_svg_url
    
    # Step 1: Detect language
    lang = language if language != "auto" else detect_language(code)
    status = f"✓ Language: {lang}\n"
    status += f"✓ Code length: {len(code)} characters\n"
    status += f"✓ Lines: {len(code.splitlines())}\n\n"
    
    # Step 2: Analyze structure
    status += "🔍 Analyzing code structure...\n"
    structure = analyze_code_structure(code, lang)
    status += f"✓ Found {structure['function_count']} functions, {structure['total_lines']} lines\n"
    
    # Step 3: Create chunks
    status += "📦 Creating smart chunks...\n"
    chunks = create_chunks(structure, code)
    structure['chunks'] = chunks
    status += f"✓ Split into {len(chunks)} chunks\n"
    
    # Step 4: Generate flowcharts for each chunk
    status += "🤖 Generating flowcharts with LLM...\n"
    chunk_flowcharts = []
    for i, chunk in enumerate(chunks):
        status += f"  Processing: {chunk['name']} (complexity: {chunk['complexity']})\n"
        flowchart = generate_flowchart_for_chunk(chunk, i, len(chunks))
        chunk_flowcharts.append(flowchart)
    
    status += "✓ All chunks processed\n"
    
    # Step 5: Combine if multiple chunks
    status += "🔗 Combining flowcharts...\n"
    if len(chunks) > 1:
        final_mermaid = combine_flowcharts(chunk_flowcharts, structure)
    else:
        final_mermaid = chunk_flowcharts[0]
    
    current_mermaid_code = final_mermaid
    status += "✓ Flowchart combined\n"
    
    # Step 6: Render
    status += "🎨 Rendering SVG...\n"
    html_svg = mermaid_to_svg(final_mermaid)
    
    # Generate SVG URL
    encoded = base64.urlsafe_b64encode(final_mermaid.encode('utf-8')).decode('utf-8')
    current_svg_url = f"https://mermaid.ink/svg/{encoded}"
    
    status += "✅ Complete!\n"
    
    # Add complexity analysis
    total_complexity = sum(c['complexity'] for c in chunks)
    status += f"\n📊 Analysis:\n"
    status += f"  - Total Complexity: {total_complexity}\n"
    status += f"  - Functions: {structure['function_count']}\n"
    status += f"  - Code Lines: {structure['total_lines']}\n"
    
    analysis = {
        "total_complexity": total_complexity,
        "function_count": structure['function_count'],
        "total_lines": structure['total_lines'],
        "chunks": len(chunks),
        "language": lang
    }
    # Auto-save log
    try:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "code": code[:500] + "..." if len(code) > 500 else code,  # Truncate long code
            "language": lang,
            "svg_url": current_svg_url,
            "mermaid_code": final_mermaid,
            "analysis": analysis
        }
        
        log_file = LOGS_DIR / f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save log: {e}")
    
    return {
        "success": True,
        "html_svg": html_svg,
        "mermaid_code": final_mermaid,
        "status": status,
        "svg_url": current_svg_url,
        "analysis": analysis
    }

@app.get("/current")
async def get_current():
    """Get current flowchart data"""
    if not current_svg_url:
        raise HTTPException(status_code=404, detail="No flowchart generated yet")
    
    return {
        "svg_url": current_svg_url,
        "mermaid_code": current_mermaid_code
    }

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    if session_id not in code_storage:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del code_storage[session_id]
    
    return {
        "success": True,
        "message": "Session deleted successfully"
    }

# ============================================
# UTILITY ENDPOINTS
# ============================================
@app.get("/logs")
async def get_logs():
    """Get all saved logs"""
    try:
        log_files = sorted(LOGS_DIR.glob("log_*.json"), reverse=True)
        logs = []
        
        for log_file in log_files[:50]:  # Return last 50 logs
            with open(log_file, 'r', encoding='utf-8') as f:
                logs.append(json.load(f))
        
        return {"success": True, "logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading logs: {str(e)}")

@app.post("/convert-to-json")
async def convert_code_to_json(code: str = Form(...)):
    """
    Utility endpoint: Convert raw code to JSON-safe string
    """
    json_safe = sanitize_code_to_json_string(code)
    payload = create_json_payload(json_safe, "auto")
    
    return {
        "success": True,
        "json_safe_code": json_safe,
        "json_payload": payload,
        "example_curl": f'curl -X POST "http://localhost:8000/generate" -H "Content-Type: application/json" -d \'{json.dumps(payload)}\''
    }

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("🚀 Code2Flow API v4.0 - Enhanced with Separate Endpoints!")
    print("="*70)
    print("✨ New Features:")
    print("  1. POST /submit-code - Submit your code")
    print("  2. POST /set-language/{session_id} - Set language (optional)")
    print("  3. POST /generate-flowchart/{session_id} - Generate flowchart")
    print("")
    print("🔥 Or use the original all-in-one:")
    print("  POST /generate - Direct generation")
    print("")
    print("📚 Open: http://localhost:8000/")
    print("📖 Docs: http://localhost:8000/docs")
    print("="*70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)