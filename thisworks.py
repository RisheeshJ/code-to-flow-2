# production_code2flow.py - Hybrid Tree-sitter + LLM approach for production code
import base64
import webbrowser
import re
import time
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
    model=os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct"),
    api_key=key,
    temperature=0.1
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

def generate_flowchart_for_chunk(chunk, chunk_index, total_chunks, max_retries=3):
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
