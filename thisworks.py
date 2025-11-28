# production_code2flow.py - Hybrid Tree-sitter + LLM approach for production code
import gradio as gr
import base64
import webbrowser
import re
from tree_sitter import Parser, Language
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_c as tsc


from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_groq import ChatGroq
load_dotenv()
import os
key = os.getenv("GROQ_API_KEY")


# =====================
# CONFIG
# =====================
llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    api_key=key,
    temperature=0.2
)

# Test connection (remove after testing)
try:
    test_response = llm.invoke("Say 'API connected!'")
    print(f"✅ Groq API working: {test_response.content}")
except Exception as e:
    print(f"❌ API Error: {e}")
# Setup parsers
PY_LANG = Language(tspython.language())
JS_LANG = Language(tsjavascript.language())
C_LANG = Language(tsc.language())

p_py = Parser(PY_LANG)
p_js = Parser(JS_LANG)
p_c = Parser(C_LANG)

# Global storage
current_svg_url = ""
current_mermaid_code = ""

# =====================
# STEP 1: STATIC ANALYSIS
# =====================

def detect_language(code):
    s = code.strip()
    if s.startswith(("def ", "class ", "import ", "from ", "async ")):
        return "python"
    if s.startswith("#include") or " main(" in s:
        return "c"
    if "function " in s or "const " in s or "=>" in s or "class " in s:
        return "javascript"
    return "python"

class FunctionInfo:
    def __init__(self, name, start_line, end_line, code, has_loops=False, has_conditionals=False, calls=None):
        self.name = name
        self.start_line = start_line
        self.end_line = end_line
        self.code = code
        self.has_loops = has_loops
        self.has_conditionals = has_conditionals
        self.calls = calls or []
        self.complexity = self.calculate_complexity()
    
    def calculate_complexity(self):
        """Calculate cyclomatic complexity estimate"""
        complexity = 1
        complexity += self.code.count('if ')
        complexity += self.code.count('elif ')
        complexity += self.code.count('for ')
        complexity += self.code.count('while ')
        complexity += self.code.count('and ')
        complexity += self.code.count('or ')
        return complexity

def extract_function_node_info(node, code_bytes, lang):
    """Extract function name, body, and metadata"""
    name = "unknown"
    start_line = node.start_point[0]
    end_line = node.end_point[0]
    
    # Get function name
    for child in node.children:
        if child.type == 'identifier' or child.type == 'property_identifier':
            name = code_bytes[child.start_byte:child.end_byte].decode('utf8', errors='ignore')
            break
    
    # Get full code
    code = code_bytes[node.start_byte:node.end_byte].decode('utf8', errors='ignore')
    
    # Analyze complexity
    has_loops = any(c.type in ('for_statement', 'while_statement', 'for_in_statement') 
                    for c in node.children)
    has_conditionals = any(c.type == 'if_statement' for c in node.children)
    
    # Extract function calls
    calls = []
    def find_calls(n):
        if n.type == 'call':
            for c in n.children:
                if c.type in ('identifier', 'attribute'):
                    call_name = code_bytes[c.start_byte:c.end_byte].decode('utf8', errors='ignore')
                    if call_name not in ['print', 'len', 'range', 'str', 'int', 'float']:
                        calls.append(call_name)
        for child in n.children:
            find_calls(child)
    
    find_calls(node)
    
    return FunctionInfo(name, start_line, end_line, code, has_loops, has_conditionals, calls)

def analyze_code_structure(code, lang):
    """Extract all functions and their relationships"""
    code_bytes = code.encode('utf8')
    
    if lang == "python":
        tree = p_py.parse(code_bytes)
    elif lang == "javascript":
        tree = p_js.parse(code_bytes)
    elif lang == "c":
        tree = p_c.parse(code_bytes)
    else:
        tree = p_py.parse(code_bytes)
    
    functions = []
    main_code = []
    
    def traverse(node, depth=0):
        if depth > 20:
            return
        
        # Extract functions
        if node.type in ('function_definition', 'function_declaration', 'method_definition'):
            func_info = extract_function_node_info(node, code_bytes, lang)
            functions.append(func_info)
        
        # Extract top-level code (not in functions)
        elif node.type in ('expression_statement', 'assignment') and depth <= 2:
            code_snippet = code_bytes[node.start_byte:node.end_byte].decode('utf8', errors='ignore')
            main_code.append(code_snippet.split('\n')[0][:80])
        
        for child in node.children:
            if child.is_named:
                traverse(child, depth + 1)
    
    traverse(tree.root_node)
    
    return {
        'functions': functions,
        'main_code': main_code,
        'total_lines': len(code.split('\n')),
        'function_count': len(functions)
    }

# =====================
# STEP 2: SMART CHUNKING
# =====================

def create_chunks(structure, code, max_chunk_size=500):
    """Split large code into manageable chunks for LLM"""
    chunks = []
    
    # If code is small, send as one chunk
    if structure['total_lines'] <= max_chunk_size:
        chunks.append({
            'type': 'full',
            'code': code,
            'name': 'Main Flow',
            'complexity': sum(f.complexity for f in structure['functions'])
        })
        return chunks
    
    # Otherwise, chunk by function
    for func in structure['functions']:
        chunks.append({
            'type': 'function',
            'code': func.code,
            'name': func.name,
            'complexity': func.complexity,
            'calls': func.calls,
            'has_loops': func.has_loops,
            'has_conditionals': func.has_conditionals
        })
    
    # Add main code chunk if exists
    if structure['main_code']:
        main_chunk_code = '\n'.join(structure['main_code'])
        chunks.append({
            'type': 'main',
            'code': main_chunk_code,
            'name': 'Main Execution',
            'complexity': 1
        })
    
    return chunks

# =====================
# STEP 3: LLM FLOWCHART GENERATION
# =====================

def generate_flowchart_for_chunk(chunk, chunk_index, total_chunks):
    """Generate Mermaid flowchart for a single chunk using LLM"""
    
    chunk_type = chunk['type']
    chunk_name = chunk['name']
    code = chunk['code']
    
    # Create contextual prompt based on chunk metadata
    context = ""
    if chunk.get('has_loops'):
        context += "This code contains loops - use proper loop back-edges. "
    if chunk.get('has_conditionals'):
        context += "This code has conditionals - use diamond decision nodes. "
    if chunk.get('calls'):
        context += f"This calls: {', '.join(chunk['calls'][:5])}. "
    
    prompt = f"""You are an expert flowchart generator. Convert this code into a Mermaid flowchart.

CODE CONTEXT:
- Function/Section: {chunk_name}
- Type: {chunk_type}
- Complexity: {chunk.get('complexity', 1)}
- {context}

CRITICAL MERMAID RULES:
1. Start with: graph TD
2. Use UNIQUE node IDs starting with {chr(65 + chunk_index)} (e.g., A1, A2, B1, B2)
3. Node shapes:
   - Start/End: ID([Label])
   - Process: ID[Label]
   - Decision: ID{{"Label?"}}
   - Loop: ID[/"Label"/]
4. For loops: MUST show back-edge (LoopEnd --> LoopStart)
5. For if/else: Show TRUE and FALSE branches with |Yes| and |No| labels
6. Keep labels SHORT (max 40 chars)
7. Show all important logic flow

EXAMPLE for loop:
```mermaid
graph TD
    A1([Start Loop])
    A2{{"i < 10?"}}
    A3[Process i]
    A4[i++]
    A5([End])
    
    A1 --> A2
    A2 -->|Yes| A3
    A3 --> A4
    A4 --> A2
    A2 -->|No| A5
```

CODE TO CONVERT:
```
{code}
```

Generate ONLY the mermaid code (no explanations):"""
    
    try:
        result = llm.invoke(prompt).content.strip()
        
        # Extract mermaid code
        if "```mermaid" in result:
            start = result.find("```mermaid") + 10
            end = result.find("```", start)
            if end != -1:
                result = result[start:end].strip()
        elif "```" in result:
            start = result.find("```") + 3
            end = result.find("```", start)
            if end != -1:
                result = result[start:end].strip()
        
        # Ensure starts with graph TD
        if not result.startswith("graph TD") and not result.startswith("flowchart TD"):
            result = "graph TD\n" + result
        
        return result.strip()
    
    except Exception as e:
        print(f"Error generating flowchart: {e}")
        return f"graph TD\n    ERR[Error: {chunk_name}]"

def combine_flowcharts(chunk_flowcharts, structure):
    """Combine multiple flowcharts into one master flowchart with subgraphs"""
    
    if len(chunk_flowcharts) == 1:
        return chunk_flowcharts[0]
    
    # Build master flowchart with subgraphs
    lines = ["graph TD"]
    lines.append("    START([Program Start])")
    
    # Add each function as a subgraph
    for i, (chunk, flowchart) in enumerate(zip(structure['chunks'], chunk_flowcharts)):
        chunk_name = chunk['name'].replace(' ', '_')
        
        # Extract nodes from chunk flowchart (skip "graph TD" line)
        chunk_lines = [line for line in flowchart.split('\n') if line.strip() and not line.strip().startswith(('graph', 'flowchart'))]
        
        # Add subgraph
        lines.append(f"    subgraph SUB{i}[{chunk['name']}]")
        lines.extend([f"    {line}" for line in chunk_lines])
        lines.append("    end")
    
    # Connect main flow
    lines.append("    START --> SUB0")
    for i in range(len(chunk_flowcharts) - 1):
        lines.append(f"    SUB{i} --> SUB{i+1}")
    
    lines.append("    SUB" + str(len(chunk_flowcharts)-1) + " --> END([Program End])")
    
    return '\n'.join(lines)

# =====================
# STEP 4: RENDERING
# =====================

def mermaid_to_svg(mermaid_code):
    """Convert Mermaid to SVG using mermaid.ink"""
    global current_svg_url
    
    try:
        encoded = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
        current_svg_url = f"https://mermaid.ink/svg/{encoded}"
        
        return f'''
        <div style="overflow:auto; max-height:700px; border:1px solid #666;
                    border-radius:8px; padding:10px; background:#fafafa;">
            <img src="{current_svg_url}" alt="Flowchart" style="max-width:100%; display:block;" 
                 onerror="this.parentElement.innerHTML='<p style=color:red;padding:20px;>❌ Error loading flowchart</p>'">
        </div>
        '''
    except Exception as e:
        return f'<div style="color:red; padding:10px;">❌ Error: {str(e)}</div>'

# =====================
# MAIN PROCESSING PIPELINE
# =====================

def process_production_code(code, lang_choice):
    """Full production pipeline"""
    global current_mermaid_code
    
    if not code.strip():
        return "⚠️ Please enter code", "", "No code provided"
    
    try:
        # Step 1: Detect language
        lang = lang_choice if lang_choice != "auto" else detect_language(code)
        status = f"✓ Language: {lang}\n"
        
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
        status += "✅ Complete!\n"
        
        # Add complexity analysis
        total_complexity = sum(c['complexity'] for c in chunks)
        status += f"\n📊 Analysis:\n"
        status += f"  - Total Complexity: {total_complexity}\n"
        status += f"  - Functions: {structure['function_count']}\n"
        status += f"  - Code Lines: {structure['total_lines']}\n"
        
        return html_svg, final_mermaid, status
    
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        return f'<div style="color:red; padding:10px;">{error_msg}</div>', "", error_msg

def open_in_browser():
    """Open flowchart in browser"""
    if current_svg_url:
        webbrowser.open(current_svg_url)
        return "✅ Opened in browser!"
    return "⚠️ Generate flowchart first!"

print('hello, i am working')
# # =====================
# # GRADIO UI
# # =====================

# with gr.Blocks(theme=gr.themes.Soft(), title="Code2Flow",css="""
# .meta-text {display:none !important;}          /* hides completed-in-Xs */
# .progress-text {display:none !important;}      /* hides `Processing...` text */
# .progress-bar, .progress {display:none !important;}  /* hides spinner/countdown */
# .svelte-dq9f7a, .svelte-1ipelgc {display:none !important;} /* hides new gradio v4 loading UI */
# """
# ) as demo:
#     gr.Markdown("## Code2Flow")
#     gr.Markdown("Uses Tree-sitter + LLM approach for code")
    
#     with gr.Row():
#         with gr.Column(scale=1):
#             code_input = gr.Textbox(
#                 label="📝 Paste Code",
#                 placeholder="Paste your code here...",
#                 lines=18,
#             )
            
#             lang_choice = gr.Radio(
#                 choices=["auto", "python", "javascript", "c"],
#                 value="auto",
#                 label="Language"
#             )
            
#             with gr.Row():
#                 generate_btn = gr.Button("🚀 Generate Flowchart", variant="primary", size="lg")
#                 open_btn = gr.Button("🌐 Open in Browser", variant="secondary")
            
#             status_output = gr.Textbox(label="📊 Analysis & Status", lines=12, interactive=False)
            
          
    
#         with gr.Column(scale=2):
#             flowchart_output = gr.HTML(label="🔀 Production Flowchart")
            
#             with gr.Accordion("🔍 Generated Mermaid Code", open=False):
#                 mermaid_output = gr.Code(label="Mermaid Code", language="markdown", lines=15)
    
#     generate_btn.click(
#         fn=process_production_code,
#         inputs=[code_input, lang_choice],
#         outputs=[flowchart_output, mermaid_output, status_output]
#     )
    
#     open_btn.click(
#         fn=open_in_browser,
#         inputs=None,
#         outputs=status_output
#     )
    
#     gr.Examples(
#         examples=[
#             ["""def fibonacci(n):
#     if n <= 1:
#         return n
#     return fibonacci(n-1) + fibonacci(n-2)

# def process_numbers(limit):
#     results = []
#     for i in range(limit):
#         if i % 2 == 0:
#             results.append(fibonacci(i))
#         else:
#             results.append(i * 2)
#     return results

# data = process_numbers(10)
# print(f"Results: {data}")""", "python"],
#             ["""class Calculator:
#     def __init__(self):
#         self.result = 0
    
#     def calculate(self, a, b, operation):
#         if operation == "add":
#             self.result = a + b
#         elif operation == "multiply":
#             self.result = a * b
#         else:
#             self.result = 0
#         return self.result

# calc = Calculator()
# while True:
#     op = input("Operation: ")
#     if op == "quit":
#         break
#     x = int(input("First number: "))
#     y = int(input("Second number: "))
#     result = calc.calculate(x, y, op)
#     print(f"Result: {result}")""", "python"]
#         ],
#         inputs=[code_input, lang_choice],
#         label="📚 Production Code Examples"
#     )

# if __name__ == "__main__":
#     demo.launch(share=True, server_name="127.0.0.1")