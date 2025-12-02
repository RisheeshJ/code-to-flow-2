# streamlit_app.py - Simple Streamlit UI for Code2Flow API with File Upload
import streamlit as st
import requests
import webbrowser
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
import os

# Configuration - works both locally and on Render
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# ============================================
# SESSION STATE INITIALIZATION
# ============================================
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'flowchart_generated' not in st.session_state:
    st.session_state.flowchart_generated = False
if 'svg_url' not in st.session_state:
    st.session_state.svg_url = None
if 'mermaid_code' not in st.session_state:
    st.session_state.mermaid_code = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = None
if 'status' not in st.session_state:
    st.session_state.status = None
if 'uploaded_code' not in st.session_state:
    st.session_state.uploaded_code = ""
if 'file_name' not in st.session_state:
    st.session_state.file_name = None

# ============================================
# API FUNCTIONS
# ============================================

def submit_code(code):
    """Submit code to API and get session ID"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/submit-code",
            data={"code": code}
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Make sure FastAPI is running on http://localhost:8000")
        return None
    except Exception as e:
        st.error(f"❌ Error submitting code: {str(e)}")
        return None

def set_language(session_id, language):
    """Set language for session"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/set-language/{session_id}",
            json={"language": language}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"❌ Error setting language: {str(e)}")
        return None

def generate_flowchart(session_id):
    """Generate flowchart for session"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/generate-flowchart/{session_id}"
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"❌ Error generating flowchart: {str(e)}")
        return None

def check_api_health():
    """Check if API is running"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=2)
        return response.status_code == 200
    except:
        return False


def get_logs():
    """Get all saved logs"""
    try:
        response = requests.get(f"{API_BASE_URL}/logs")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"❌ Error loading logs: {str(e)}")
        return None

# ============================================
# STREAMLIT UI
# ============================================

# Page config
st.set_page_config(
    page_title="Code2Flow - Visual Flowchart Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Remove default Streamlit padding */
    .block-container {
        padding-top: 2.3rem !important;
        padding-bottom: 0rem !important;
    }
    
    .main-header {
        font-size: 1.8rem;
        font-weight: bold;
        color: #2563eb;
        text-align: center;
        margin-top: -0.3rem;
        margin-bottom: 0.2rem;
        padding-top: 0;
    }
    .subtitle {
        text-align: center;
        color: #64748b;
        margin-bottom: 0.5rem;
        margin-top: 0;
        font-size: 0.9rem;
    }
    .status-box {
        background-color: #f8fafc;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3b82f6;
    }
    .success-box {
        background-color: #f0fdf4;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #22c55e;
    }
    .stButton>button {
        width: 100%;
    }
    
    /* Reduce spacing between elements */
    h3 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">📊 Code2Flow</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Transform your code into beautiful flowcharts for better understanding</div>', unsafe_allow_html=True)

# Check API status
api_healthy = check_api_health()

if not api_healthy:
    st.error("⚠️ **API Server Not Running!**")
    st.info("Please start the FastAPI server first:\n```bash\npython apicodenew.py\n```")
    st.stop()

# Success indicator
with st.sidebar:
    st.markdown("---")
    
    if st.button("📋 View Logs", use_container_width=True):
        logs_data = get_logs()
        if logs_data and logs_data.get('success'):
            st.session_state.show_logs = True
        else:
            st.error("No logs found")
    
    
    # Info section
    st.markdown("### 📊 How it works")
    st.markdown("""
    1. **Paste** your code or **Upload** a code file
    2. **Select** language or leave as "auto" for automatic language detection
    3. **Generate** flowchart
    4. **View** & Download
    """)
    
    st.markdown("---")
    
    
    
    
    
# Main content area
col1, col2 = st.columns([1, 1])

# Left column - Input
with col1:
    st.markdown("### 📝 Code Input")
    
    # File upload section
    st.markdown("**Upload a code file (optional):**")
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=['py', 'js', 'c', 'txt', 'ts'],
        help="Upload a Python, JavaScript, C, TypeScript, or text file containing your code"
    )
    
    # Handle file upload and read content
    if uploaded_file is not None:
        try:
            # Read file content
            bytes_data = uploaded_file.getvalue()
            try:
                file_content = bytes_data.decode('utf-8')
            except UnicodeDecodeError:
                file_content = bytes_data.decode('latin-1')
            
            # Store in session state
            st.session_state.uploaded_code = file_content
            st.session_state.file_name = uploaded_file.name
            
            st.success(f"✅ Loaded '{uploaded_file.name}' ({len(file_content.splitlines())} lines)")
            
        except Exception as e:
            st.error(f"❌ Error reading file: {str(e)}")
            st.session_state.uploaded_code = ""
            st.session_state.file_name = None
    
    # Code input text area - ALWAYS uses uploaded_code as value
    st.markdown("**Enter or edit your code below:**")
    code_input = st.text_area(
        "Code Editor",
        value=st.session_state.uploaded_code,
        height=400,
        placeholder="Paste your code here or upload a file above...",
        key="code_area"
    )
    
    # Language selection
    language = st.selectbox(
        "Select Language:",
        options=["auto", "python", "javascript", "c", "typescript"],
        index=0,
        help="Choose 'auto' for automatic detection"
    )
    
    # Generate button
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        generate_btn = st.button(
            "🚀 Generate Flowchart",
            type="primary"
        )
    
    with col_btn2:
        clear_btn = st.button(
            "🗑️ Clear All"
        )
    
    if clear_btn:
        # Clear all session state
        st.session_state.session_id = None
        st.session_state.flowchart_generated = False
        st.session_state.svg_url = None
        st.session_state.mermaid_code = None
        st.session_state.analysis = None
        st.session_state.status = None
        st.session_state.uploaded_code = ""
        st.session_state.file_name = None
        st.rerun()
    
    # Processing logic
    if generate_btn:
        if not code_input.strip():
            st.error("❌ Please enter some code or upload a file!")
        else:
            with st.spinner("⏳ Processing..."):
                # Step 1: Submit code
                progress_text = st.empty()
                progress_text.info("📤 Step 1/3: Submitting code...")
                
                result = submit_code(code_input)
                if result and result.get('success'):
                    st.session_state.session_id = result['session_id']
                    
                    # Step 2: Set language
                    progress_text.info("🔧 Step 2/3: Setting language...")
                    lang_result = set_language(st.session_state.session_id, language)
                    
                    if lang_result and lang_result.get('success'):
                        # Step 3: Generate flowchart
                        progress_text.info("🎨 Step 3/3: Generating flowchart...")
                        
                        flowchart_result = generate_flowchart(st.session_state.session_id)
                        
                        if flowchart_result and flowchart_result.get('success'):
                            st.session_state.flowchart_generated = True
                            st.session_state.svg_url = flowchart_result['svg_url']
                            st.session_state.mermaid_code = flowchart_result['mermaid_code']
                            st.session_state.analysis = flowchart_result['analysis']
                            st.session_state.status = flowchart_result['status']
                            
                            progress_text.success("✅ Flowchart generated successfully!")
                            st.rerun()
                        else:
                            progress_text.error("❌ Failed to generate flowchart")
                    else:
                        progress_text.error("❌ Failed to set language")
                else:
                    progress_text.error("❌ Failed to submit code")

# Right column - Output
with col2:
    st.markdown("### 🎨 Flowchart Output")
    
    if st.session_state.flowchart_generated:
        # Display flowchart
        try:
            st.image(
                st.session_state.svg_url,
                caption="Generated Flowchart"
            )
            
            # Action buttons
            col_action1, col_action2 = st.columns(2)
            
            with col_action1:
                st.link_button("🌐 Open in Browser", st.session_state.svg_url)
            
            with col_action2:
                st.download_button(
                    label="📋 Download URL",
                    data=st.session_state.svg_url,
                    file_name="flowchart_url.txt",
                    mime="text/plain"
                )
            
            # Analysis
            if st.session_state.analysis:
                st.markdown("---")
                st.markdown("### 📊 Code Analysis")
                
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                
                with col_stat1:
                    st.metric(
                        "Functions",
                        st.session_state.analysis.get('function_count', 0)
                    )
                
                with col_stat2:
                    st.metric(
                        "Total Lines",
                        st.session_state.analysis.get('total_lines', 0)
                    )
                
                with col_stat3:
                    st.metric(
                        "Complexity",
                        st.session_state.analysis.get('total_complexity', 0)
                    )
                
                # Language detected
                st.info(f"**Language Detected:** `{st.session_state.analysis.get('language', 'unknown')}`")
            
            # Mermaid code accordion
            with st.expander("📄 View Mermaid Code"):
                st.code(st.session_state.mermaid_code, language="markdown")
                
                st.download_button(
                    label="💾 Download .mmd file",
                    data=st.session_state.mermaid_code,
                    file_name=f"flowchart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mmd",
                    mime="text/plain",
                    key="download_mermaid_btn"
                )
            
            # Status log accordion
            if st.session_state.status:
                with st.expander("📋 View Processing Log"):
                    st.code(st.session_state.status, language="text")
        
        except Exception as e:
            st.error(f"❌ Error displaying flowchart: {str(e)}")
    
    else:
        # Placeholder
        st.info("👈 Enter your code or upload a file and click **Generate Flowchart** to see the result here")
        
        st.markdown("---")
        st.markdown("### ✨ Features")
        st.markdown("""
        - 📁 **File Upload Support** - Upload .py, .js, .c, .txt, .ts files
        - 📝 **Direct Code Input** - Paste or type code directly
        - ✏️ **Edit Uploaded Files** - Modify uploaded code before generation
        - 🔍 **Smart Code Analysis** - Detects functions, loops, and conditionals
        - 🎯 **Multi-Language Support** - Python, JavaScript, C, TypeScript
        - 🧩 **Complexity Detection** - Analyzes code complexity
        - 📊 **Visual Flowcharts** - Beautiful Mermaid diagrams
        - 🚀 **Fast Processing** - Powered by LLM + Tree-sitter
        """)

# Logs viewer modal
if st.session_state.get('show_logs', False):
    st.markdown("---")
    st.markdown("### 📋 Saved Logs")
    
    logs_data = get_logs()
    if logs_data and logs_data.get('logs'):
        for i, log in enumerate(logs_data['logs']):
            with st.expander(f"🕐 {log['timestamp']} - {log['language']}"):
                st.code(log['code'], language=log['language'])
                st.markdown(f"**Flowchart:** [View SVG]({log['svg_url']})")
                st.metric("Functions", log['analysis']['function_count'])
                st.metric("Lines", log['analysis']['total_lines'])
    
    if st.button("❌ Close Logs"):
        st.session_state.show_logs = False
        st.rerun()

# Footer
st.markdown("---")
st.markdown(
    '<div style="text-align: center; color: #94a3b8;">Made with ❤️ using Streamlit | Code2Flow v4.0</div>',
    unsafe_allow_html=True
)
