import os
from typing import List, Optional, get_args
from dataclasses import dataclass, field
from tree_sitter_language_pack import get_parser, SupportedLanguage

# --- CONFIGURATION ---
IGNORE_EXT = (
    '.png', '.jpg', '.jpeg', '.gif', '.exe', '.dll', '.pyc', '.o', '.obj', 
    '.css', '.svg', '.gitignore', '.csv', '.json', '.yaml', '.yml', 
    '.txt', '.lock', '.xml', '.map', '.ico', '.woff', '.woff2', '.ttf'
)

SKIP_DIRS = {
    '.git', '.github', 'node_modules', 'venv', '.venv', 'env', '__pycache__', 
    'dist', 'build', '.idea', '.vscode', 'coverage', 'tmp', 'temp', 'vendor'
}

@dataclass
class ImportInfo:
    """Represents an import statement found in the code."""
    module: str
    names: List[str]
    alias: Optional[str] = None
    is_from: bool = False
    source_line: int = 0

@dataclass
class CodeBlock:
    """Represents a strictly code-based unit (Function, Class, Method)."""
    name: str
    type: str  # 'function', 'class', 'method', 'module'
    content: str
    start_line: int
    end_line: int
    file_path: str
    identifier: str
    parent_block: Optional[str] = None
    imports: List[ImportInfo] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)

class AdvancedCodeParser:
    """
    Universal Code Parser.
    Dynamically loads languages and extracts definitions + imports for:
    Python, JS/TS, Go, Rust, Java, C++, C, C#, PHP, Ruby.
    """
    
    def __init__(self):
        # Dynamic Language Detection
        try:
            raw_args = get_args(SupportedLanguage)
            if raw_args and hasattr(raw_args[0], '__args__'):
                self.supported_langs = list(raw_args[0].__args__)
            else:
                self.supported_langs = list(raw_args)
        except Exception as e:
            print(f"Warning: Could not dynamically load languages: {e}. Defaulting to common set.")
            self.supported_langs = [
                "python", "javascript", "typescript", "tsx", "go", "rust", 
                "java", "cpp", "c", "c_sharp", "php", "ruby"
            ]

    def filter_process(self, file_path: str) -> bool:
        """Filters files based on the IGNORE_EXT and SKIP_DIRS rules."""
        parts = file_path.split(os.sep)
        if any(part in SKIP_DIRS for part in parts):
            return False
        _, ext = os.path.splitext(file_path)
        if ext.lower() in IGNORE_EXT:
            return False
        return True

    def _get_language(self, file_path: str) -> Optional[str]:
        """Maps file extension to tree-sitter language name."""
        ext = file_path.split('.')[-1].lower()
        mapping = {
            "py": "python",
            "js": "javascript", "cjs": "javascript", "mjs": "javascript",
            "ts": "typescript",
            "tsx": "tsx",
            "rs": "rust",
            "go": "go",
            "java": "java",
            "cpp": "cpp", "cc": "cpp", "cxx": "cpp", "h": "cpp", "hpp": "cpp",
            "c": "c",
            "cs": "c_sharp",
            "rb": "ruby",
            "php": "php",
        }
        lang = mapping.get(ext)
        if lang in self.supported_langs:
            return lang
        return None

    def parse_file(self, file_path: str, content: bytes = None) -> List[CodeBlock]:
        """
        Parses a file if it matches the 'Code' criteria.
        Returns a list of logical blocks (Classes, Functions).
        """
        if not self.filter_process(file_path):
            return []

        lang = self._get_language(file_path)
        if not lang:
            return []

        if content is None:
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                return []
        
        _, ext = os.path.splitext(file_path)
        if ext.lower() == ".md":
            text_content = content.decode('utf-8', errors='ignore')
            file_name = os.path.basename(file_path)
            return [CodeBlock(
                name=file_name,
                type="module", 
                content=text_content,
                start_line=0,
                end_line=len(text_content.splitlines()),
                file_path=os.path.relpath(file_path),
                identifier=f"{os.path.relpath(file_path)}::root::{file_name}",
                parent_block=None
            )]

        parser = get_parser(lang)
        if not parser:
            return []

        try:
            tree = parser.parse(content)
            root = tree.root_node
            
            blocks = []
            
            # 1. Global Imports
            file_imports = self._extract_imports(root, content, lang)
            
            # 2. Walk Tree for Definitions
            self._visit_node(root, content, blocks, file_path, lang, parent_scope=None)
            
            # 3. Attach Context
            for block in blocks:
                if not block.imports:
                    block.imports = file_imports
            
            return blocks
            
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return []

    def _visit_node(self, node, content: bytes, blocks: List[CodeBlock], file_path: str, lang: str, parent_scope: str):
        """Recursive AST walker to find Definitions."""
        block_created = None
        new_scope = parent_scope

        # --- PYTHON ---
        if lang == "python":
            if node.type in ["function_definition", "class_definition"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)
        
        # --- JS / TS / TSX ---
        elif lang in ["javascript", "typescript", "tsx"]:
            if node.type in ["function_declaration", "class_declaration", "method_definition", "arrow_function"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)
            elif node.type == "variable_declarator":
                val = node.child_by_field_name('value')
                if val and val.type in ["arrow_function", "function"]:
                     block_created = self._process_def_node(node, content, file_path, parent_scope, lang)

        # --- GO ---
        elif lang == "go":
            if node.type in ["function_declaration", "method_declaration", "type_declaration"]:
                if node.type == "type_declaration":
                    for child in node.children:
                        if child.type == "type_spec":
                            block_created = self._process_def_node(child, content, file_path, parent_scope, lang)
                else:
                    block_created = self._process_def_node(node, content, file_path, parent_scope, lang)

        # --- JAVA / C# ---
        elif lang in ["java", "c_sharp"]:
            if node.type in ["class_declaration", "method_declaration", "interface_declaration", "enum_declaration"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)

        # --- C++ / C ---
        elif lang in ["cpp", "c"]:
            if node.type in ["function_definition", "class_specifier", "struct_specifier"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)
        
        # --- RUST ---
        elif lang == "rust":
            if node.type in ["function_item", "struct_item", "impl_item", "trait_item"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)

        # --- PHP ---
        elif lang == "php":
            if node.type in ["class_declaration", "function_definition", "method_declaration"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)

        # --- RUBY ---
        elif lang == "ruby":
            if node.type in ["class", "method", "module"]:
                block_created = self._process_def_node(node, content, file_path, parent_scope, lang)

        # Recurse
        if block_created:
            blocks.append(block_created)
            new_scope = block_created.name if not parent_scope else f"{parent_scope}.{block_created.name}"

        for child in node.children:
            self._visit_node(child, content, blocks, file_path, lang, new_scope)

    def _process_def_node(self, node, content: bytes, file_path: str, parent_scope: str, lang: str) -> Optional[CodeBlock]:
        """Extracts details from a definition node."""
        name = "anonymous"
        
        # Name Extraction
        name_node = node.child_by_field_name('name')
        
        # Special Cases
        if not name_node:
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name('name')
            elif lang == "rust" and node.type == "impl_item":
                name_node = node.child_by_field_name('type')
        
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode('utf-8')

        # Type Determination
        b_type = "function"
        if any(x in node.type for x in ["class", "struct", "interface", "impl", "type", "module"]):
            b_type = "class"
        elif "method" in node.type or (parent_scope and parent_scope != ""): 
            b_type = "method"

        body_str = content[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
        identifier = f"{os.path.relpath(file_path)}::{parent_scope if parent_scope else 'root'}::{name}"

        # Context Extraction
        calls = self._extract_calls(node, content, lang)
        bases = self._extract_bases(node, content, lang)

        return CodeBlock(
            name=name,
            type=b_type,
            content=body_str,
            start_line=node.start_point.row,
            end_line=node.end_point.row,
            file_path=os.path.relpath(file_path),
            identifier=identifier,
            parent_block=parent_scope,
            calls=calls,
            bases=bases
        )

    def _extract_imports(self, root_node, content: bytes, lang: str) -> List[ImportInfo]:
        """
        Extracts imports for all supported languages including PHP and Ruby.
        """
        imports = []
        to_visit = [root_node]
        
        while to_visit:
            curr = to_visit.pop()
            
            # --- PYTHON ---
            if lang == "python":
                if curr.type == "import_statement":
                    text = content[curr.start_byte:curr.end_byte].decode('utf-8')
                    imports.append(ImportInfo(module=text, names=["*"], source_line=curr.start_point.row))
                elif curr.type == "import_from_statement":
                    mod_node = curr.child_by_field_name('module_name')
                    mod_name = content[mod_node.start_byte:mod_node.end_byte].decode('utf-8') if mod_node else "."
                    imports.append(ImportInfo(module=mod_name, names=[], is_from=True, source_line=curr.start_point.row))

            # --- JS / TS / TSX ---
            elif lang in ["javascript", "typescript", "tsx"]:
                if curr.type == "import_statement":
                    source_node = curr.child_by_field_name('source')
                    if source_node:
                        mod_name = content[source_node.start_byte:source_node.end_byte].decode('utf-8').strip('"\'')
                        imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))

            # --- GO ---
            elif lang == "go":
                if curr.type == "import_spec":
                    path_node = curr.child_by_field_name('path')
                    if path_node:
                        mod_name = content[path_node.start_byte:path_node.end_byte].decode('utf-8').strip('"')
                        imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))

            # --- JAVA ---
            elif lang == "java":
                if curr.type == "import_declaration":
                    raw_text = content[curr.start_byte:curr.end_byte].decode('utf-8').replace('import', '').replace(';', '').strip()
                    imports.append(ImportInfo(module=raw_text, names=[], source_line=curr.start_point.row))

            # --- C# ---
            elif lang == "c_sharp":
                if curr.type == "using_directive":
                    name_node = curr.child_by_field_name('name')
                    if name_node:
                        mod_name = content[name_node.start_byte:name_node.end_byte].decode('utf-8')
                        imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))

            # --- C++ / C ---
            elif lang in ["cpp", "c"]:
                if curr.type == "preproc_include":
                    path_node = curr.child_by_field_name('path')
                    if path_node:
                        mod_name = content[path_node.start_byte:path_node.end_byte].decode('utf-8').strip('<>"')
                        imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))

            # --- RUST ---
            elif lang == "rust":
                if curr.type == "use_declaration":
                    argument = curr.child_by_field_name('argument')
                    if argument:
                        mod_name = content[argument.start_byte:argument.end_byte].decode('utf-8')
                        imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))
            
            # --- PHP ---
            elif lang == "php":
                if curr.type == "namespace_use_declaration":
                    # use Foo\Bar;
                    for child in curr.children:
                        if child.type == "namespace_use_clause":
                            name_node = child.child_by_field_name('name')
                            if name_node:
                                mod_name = content[name_node.start_byte:name_node.end_byte].decode('utf-8')
                                imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))
            
            # --- RUBY ---
            elif lang == "ruby":
                # Ruby imports are method calls: require 'json'
                if curr.type == "call":
                    method = curr.child_by_field_name('method')
                    if method:
                        method_name = content[method.start_byte:method.end_byte].decode('utf-8')
                        if method_name in ['require', 'require_relative', 'load']:
                            args = curr.child_by_field_name('arguments')
                            if args:
                                mod_name = content[args.start_byte:args.end_byte].decode('utf-8').strip("('\"")
                                imports.append(ImportInfo(module=mod_name, names=[], source_line=curr.start_point.row))

            if curr.child_count > 0:
                to_visit.extend(curr.children)
                
        return imports

    def _extract_calls(self, node, content: bytes, lang: str) -> List[str]:
        """Finds function calls (Simplified traversal)."""
        calls = set()
        to_visit = [node]
        
        while to_visit:
            curr = to_visit.pop()
            
            call_text = None

            if lang == "python" and curr.type == "call":
                func_node = curr.child_by_field_name('function')
                if func_node: call_text = content[func_node.start_byte:func_node.end_byte].decode('utf-8')

            elif lang in ["javascript", "typescript", "tsx", "go", "php"] and curr.type == "call_expression":
                func_node = curr.child_by_field_name('function')
                if func_node: call_text = content[func_node.start_byte:func_node.end_byte].decode('utf-8')
            
            elif lang == "ruby" and curr.type == "call":
                method_node = curr.child_by_field_name('method')
                if method_node: call_text = content[method_node.start_byte:method_node.end_byte].decode('utf-8')

            if call_text:
                # Clean up "self.method", "Foo::bar" -> "method", "bar"
                if "." in call_text: call_text = call_text.split(".")[-1]
                if "::" in call_text: call_text = call_text.split("::")[-1]
                if "->" in call_text: call_text = call_text.split("->")[-1]
                calls.add(call_text)
            
            # Avoid recursing into child definitions
            is_def = False
            if "function" in curr.type or "class" in curr.type or "method" in curr.type: is_def = True
            
            if not is_def or curr == node: 
                to_visit.extend(curr.children)
                
        return list(calls)

    def _extract_bases(self, node, content: bytes, lang: str) -> List[str]:
        """Finds parent classes."""
        bases = []
        if lang == "python" and node.type == "class_definition":
            args = node.child_by_field_name('superclasses')
            if args:
                for child in args.children:
                    if child.type in ['identifier', 'attribute']:
                        bases.append(content[child.start_byte:child.end_byte].decode('utf-8'))
        
        elif lang in ["typescript", "tsx", "java", "php"] and "class" in node.type:
             if lang in ["typescript", "tsx", "php"]:
                 heritage = node.child_by_field_name('heritage') # PHP extends is in class_base_clause which might be child
                 # PHP specific check
                 if lang == "php":
                     # PHP: class_declaration -> class_base_clause -> name
                     for child in node.children:
                         if child.type == "class_base_clause":
                             bases.append(content[child.start_byte:child.end_byte].decode('utf-8').replace('extends', '').strip())
                 elif heritage:
                     bases.append(content[heritage.start_byte:heritage.end_byte].decode('utf-8'))
             elif lang == "java":
                 superclass = node.child_by_field_name('superclass')
                 if superclass:
                     bases.append(content[superclass.start_byte:superclass.end_byte].decode('utf-8'))
        
        elif lang == "ruby" and node.type == "class":
            superclass = node.child_by_field_name('superclass')
            if superclass:
                bases.append(content[superclass.start_byte:superclass.end_byte].decode('utf-8'))

        return bases