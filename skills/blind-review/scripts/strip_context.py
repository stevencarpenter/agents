#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tree-sitter==0.25.2",
#     "tree-sitter-python==0.25.0",
#     "tree-sitter-c==0.24.2",
#     "tree-sitter-cpp==0.23.4",
#     "tree-sitter-c-sharp==0.23.5",
#     "tree-sitter-java==0.23.5",
#     "tree-sitter-kotlin==1.1.0",
#     "tree-sitter-scala==0.26.2",
#     "tree-sitter-swift==0.7.4",
#     "tree-sitter-dart==0.1.0",
#     "tree-sitter-groovy==0.1.2",
#     "tree-sitter-go==0.25.0",
#     "tree-sitter-rust==0.24.2",
#     "tree-sitter-zig==1.1.2",
#     "tree-sitter-javascript==0.25.0",
#     "tree-sitter-typescript==0.23.2",
#     "tree-sitter-css==0.25.0",
#     "tree-sitter-scss==1.0.0",
#     "tree-sitter-json==0.24.8",
#     "tree-sitter-php==0.25.1",
#     "tree-sitter-bash==0.25.1",
#     "tree-sitter-make==1.1.1",
#     "tree-sitter-dockerfile==0.2.0",
#     "tree-sitter-toml==0.7.0",
#     "tree-sitter-yaml==0.7.2",
#     "tree-sitter-hcl==1.2.0",
#     "tree-sitter-nix==0.1.0",
#     "tree-sitter-cmake==0.7.2.post1",
#     "tree-sitter-powershell==0.26.4",
#     "tree-sitter-ruby==0.23.1",
#     "tree-sitter-perl==2.0.0",
#     "tree-sitter-julia==0.23.1",
#     "tree-sitter-elixir==0.3.5",
#     "tree-sitter-haskell==0.24.1",
#     "tree-sitter-ocaml==0.26.0",
#     "tree-sitter-fsharp==0.3.12",
#     "tree-sitter-commonlisp==0.4.1",
#     "tree-sitter-lua==0.5.0",
#     "tree-sitter-sql==0.3.11",
#     "tree-sitter-graphql==0.1.0",
#     "tree-sitter-html==0.23.2",
#     "tree-sitter-svelte==1.0.2",
#     "tree-sitter-xml==0.7.0",
# ]
# ///
"""strip_context.py: PoC comment/docstring/doc stripper for blind code review.

Produces a scratch workspace whose files have identical line and column
numbers to the originals, with all comments, docstrings, and documentation
removed. Comment characters are replaced with spaces (never deleted) so
findings in the stripped copy cite real source locations directly. Comments
and docstrings are found with tree-sitter grammars, so string, regex, and
heredoc data is never mistaken for a comment.

Subcommands:
  diff  --repo DIR --base REF --out DIR   strip base+head of files changed
                                          between REF and the worktree, and
                                          emit a comment-free unified diff
  files --out DIR PATH...                 strip individual files into OUT
  mechanical --repo DIR --base REF --out DIR
                                          write only the changed code lines,
                                          one unit per file, under anonymous
                                          labels, for context-free reviewers

Documentation files (.md/.rst/.txt/.adoc) are omitted entirely, except text
files with a known language such as CMakeLists.txt and requirements.txt. Unknown or
unparseable files are copied verbatim and flagged in manifest.json, except in
mechanical mode, which omits them because their comments cannot be removed.
"""

import argparse
import bisect
import difflib
import fnmatch
import functools
import importlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path

from tree_sitter import Language, Node, Parser, Query, QueryCursor

DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc", ".mdx"}

# Language name -> (module, function) of its grammar wheel, pinned in the header.
GRAMMARS = {
    "bash": ("tree_sitter_bash", "language"),
    "c": ("tree_sitter_c", "language"),
    "c_sharp": ("tree_sitter_c_sharp", "language"),
    "cmake": ("tree_sitter_cmake", "language"),
    "commonlisp": ("tree_sitter_commonlisp", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "css": ("tree_sitter_css", "language"),
    "dart": ("tree_sitter_dart", "language"),
    "dockerfile": ("tree_sitter_dockerfile", "language"),
    "elixir": ("tree_sitter_elixir", "language"),
    "fsharp": ("tree_sitter_fsharp", "language"),
    "fsharp_signature": ("tree_sitter_fsharp", "language_signature"),
    "go": ("tree_sitter_go", "language"),
    "graphql": ("tree_sitter_graphql", "language"),
    "groovy": ("tree_sitter_groovy", "language"),
    "haskell": ("tree_sitter_haskell", "language"),
    "hcl": ("tree_sitter_hcl", "language"),
    "html": ("tree_sitter_html", "language"),
    "java": ("tree_sitter_java", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "json": ("tree_sitter_json", "language"),
    "julia": ("tree_sitter_julia", "language"),
    "kotlin": ("tree_sitter_kotlin", "language"),
    "lua": ("tree_sitter_lua", "language"),
    "make": ("tree_sitter_make", "language"),
    "nix": ("tree_sitter_nix", "language"),
    "ocaml": ("tree_sitter_ocaml", "language_ocaml"),
    "ocaml_interface": ("tree_sitter_ocaml", "language_ocaml_interface"),
    "perl": ("tree_sitter_perl", "language"),
    "php": ("tree_sitter_php", "language_php"),
    "powershell": ("tree_sitter_powershell", "language"),
    "python": ("tree_sitter_python", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "scala": ("tree_sitter_scala", "language"),
    "scss": ("tree_sitter_scss", "language"),
    "sql": ("tree_sitter_sql", "language"),
    "svelte": ("tree_sitter_svelte", "language"),
    "swift": ("tree_sitter_swift", "language"),
    "toml": ("tree_sitter_toml", "language"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "xml": ("tree_sitter_xml", "language_xml"),
    "yaml": ("tree_sitter_yaml", "language"),
    "zig": ("tree_sitter_zig", "language"),
}

# Node kinds that are comments in at least one grammar. Each grammar's query
# uses only the kinds it defines.
COMMENT_KINDS = (
    "comment",
    "line_comment",
    "block_comment",
    "multiline_comment",
    "html_comment",
    "js_comment",
    "xml_comment",
    "bracket_comment",
    "documentation_comment",
    "haddock",
    "pod",
    "xml_doc",
    "Comment",
    "marginalia",  # SQL `/* */`
)

# Strings that are documentation: their contents are blanked, their quotes kept.
DOC_QUERIES = {
    "python": """
        (expression_statement . (string) @doc .)
        (expression_statement . (concatenated_string (string) @doc) .)
    """,
    "elixir": """
        (unary_operator (call (identifier) @_name (arguments . [(string) (sigil)] @doc .))
         (#any-of? @_name "moduledoc" "doc" "typedoc"))
    """,
    "julia": """
        (_ (string_literal) @doc . [(function_definition) (macro_definition) (struct_definition)
            (module_definition) (abstract_definition) (primitive_definition) (const_statement)
            (assignment)])
    """,
    "graphql": "(description (string_value) @doc)",
    # A string that is the whole body is the return value, not a docstring.
    "commonlisp": "(defun (defun_header) . (str_lit) @doc . (_))",
    "rust": """
        (attribute_item (attribute (identifier) @_name (string_literal) @doc) (#eq? @_name "doc"))
        (inner_attribute_item (attribute (identifier) @_name (string_literal) @doc)
         (#eq? @_name "doc"))
    """,
}

# Comments that are code: build constraints, compiler and tool directives. Each
# pattern must match the whole comment, so free text cannot ride along with a
# directive to the blind reviewer.
_REFERENCE = re.compile(
    rb"///[ \t]*<(?:reference|amd-module|amd-dependency)(?:[ \t]+[\w-]+[ \t]*=[ \t]*(?:\"[^\"\n]*\"|'[^'\n]*'))*[ \t]*/>"
)
KEEP = {
    # Only directives the go tool defines, each with the arguments it takes. An
    # embed path may hold `/` (`html/index.html`) or be quoted, but not `//`.
    "go": re.compile(
        rb"//go:build[ \t]+[\w!&|().\t ]+"
        rb'|//go:embed(?:[ \t]+(?:"[^"\n]*"|`[^`\n]*`|(?:[^\s/"`]|/(?!/))+))+'
        rb"|//go:generate[ \t][^\n]*"  # a command go generate runs
        rb"|//go:linkname[ \t]+\S+(?:[ \t]+\S+)?"
        rb"|//go:debug[ \t]+[\w.-]+=[\w.-]+(?:,[\w.-]+=[\w.-]+)*|//go:fix[ \t]+inline"
        rb"|//go:wasmimport[ \t]+\S+[ \t]+\S+|//go:wasmexport[ \t]+\S+"
        rb"|//go:(?:noinline|nosplit|noescape|norace|nocheckptr|uintptrescapes|nowritebarrierrec"
        rb"|nowritebarrier|systemstack|notinheap)"
        rb"|//line[ \t]+\S+|//export[ \t]+\w+|//extern[ \t]+\S+|// \+build(?:[ \t]+[\w!,.]+)+"
    ),
    "javascript": _REFERENCE,
    "typescript": _REFERENCE,
    "tsx": _REFERENCE,
    "ruby": re.compile(
        rb"#[ \t]*(?:frozen_string_literal|encoding|coding|warn_indent|warn_past_scope"
        rb"|shareable_constant_value)[ \t]*:[ \t]*[\w-]+[ \t]*"
    ),
    "powershell": re.compile(rb"(?i)#requires(?:[ \t]+-\w+(?:[ \t]+[\w.,@{}=';\"-]+)?)+[ \t]*"),
    "swift": re.compile(rb"//[ \t]*swift-tools-version:[ \t]*[\d.]+[ \t]*"),
    # MySQL runs `/*! ... */` and reads `/*+ ... */` as optimizer hints.
    "sql": re.compile(rb"/\*[!+][\s\S]*"),
    "dockerfile": re.compile(rb"#[ \t]*(?i:syntax|escape|check)[ \t]*=[ \t]*\S+[ \t]*"),
}
# These directives count only before the first statement.
_HEADER_DIRECTIVES = {"ruby", "dockerfile", "swift"}
_GO_OUTPUT = re.compile(rb"//[ \t]*(?:Unordered )?[Oo]utput:")
_PY_CODING = re.compile(rb"#.*?coding[:=][ \t]*[-\w.]+")
# PEP 723 inline script metadata: dependencies, so code, not commentary.
_PY_SCRIPT_BLOCK = re.compile(rb"^# /// [a-zA-Z0-9-]+\r?\n(?:#(?:| [^\r\n]*)\r?\n)+# ///\r?$", re.MULTILINE)
# HTML parses these bodies as text, so `<!-- -->` inside them is data.
_HTML_TEXT_ELEMENTS = {b"textarea", b"title", b"xmp", b"iframe", b"noembed", b"noframes", b"plaintext"}
_JS_TYPES = {
    "", "module", "text/javascript", "application/javascript", "text/ecmascript",
    "application/ecmascript", "application/x-javascript", "text/jscript", "text/babel", "text/jsx",
}
_SCRIPT_LANGS = {"js": "javascript", "javascript": "javascript", "jsx": "javascript", "ts": "typescript",
                 "typescript": "typescript", "tsx": "tsx"}
_STYLE_LANGS = {"": "css", "css": "css", "postcss": "css", "scss": "scss", "less": "scss"}
_MAKE_COMMENT = re.compile(rb"(?<!\\)#[^\r\n]*")
_DOC_CONTENT = {"string_content", "quoted_content", "content"}
_DOC_QUOTE = re.compile(rb'[^"\'`]*("""|\'\'\'|"|\'|`)')


@functools.cache
def _language_object(lang: str) -> Language:
    module, function = GRAMMARS[lang]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # older wheels return an int pointer
        return Language(getattr(importlib.import_module(module), function)())


@functools.cache
def _queries(lang: str) -> tuple[Query, Query | None]:
    language = _language_object(lang)
    kinds = [k for k in COMMENT_KINDS if language.id_for_node_kind(k, True) is not None]
    comments = Query(language, "[" + " ".join(f"({k})" for k in kinds) + "] @comment")
    docs = DOC_QUERIES.get(lang)
    return comments, Query(language, docs) if docs else None


def _captures(query: Query, node: Node, name: str) -> list[Node]:
    return QueryCursor(query).captures(node).get(name, [])


def _docstrings(lang: str, root: Node) -> list[Node]:
    """Return the docstring nodes; a string that interpolates runs code, so it is not one."""
    docs = _queries(lang)[1]
    if docs is None:
        return []
    return [n for n in _captures(docs, root, "doc") if not any("interpolation" in c.type for c in n.children)]


def _kept(lang: str, node: Node, data: bytes, py_blocks: list[range]) -> bool:
    """Return True when a comment node carries code, so it must stay."""
    text = data[node.start_byte : node.end_byte].rstrip()
    if node.start_byte == 0 and text.startswith(b"#!"):
        return True
    keep = KEEP.get(lang)
    if keep is not None and keep.fullmatch(text) and (node.start_point.column == 0 or lang == "sql"):
        if lang not in _HEADER_DIRECTIVES:
            return True
        prev = node.prev_named_sibling
        while prev is not None and prev.type in COMMENT_KINDS:
            prev = prev.prev_named_sibling
        return prev is None
    if lang == "python":
        return (node.start_point.row < 2 and _PY_CODING.match(text) is not None) or any(
            node.start_byte in block for block in py_blocks
        )
    if lang == "go":
        return _go_output(node, data) or _cgo_preamble(node, data)
    return False


def _cgo_preamble(node: Node, data: bytes) -> bool:
    """A cgo preamble is C code in the comments just before `import "C"`."""
    nxt = node.next_named_sibling
    while nxt is not None and nxt.type == "comment":
        nxt = nxt.next_named_sibling
    return nxt is not None and nxt.type == "import_declaration" and b'"C"' in data[nxt.start_byte : nxt.end_byte]


def _go_output(node: Node, data: bytes) -> bool:
    """`go test` compares an Example function's `// Output:` comments with its stdout."""
    func = node.parent
    while func is not None and func.type != "function_declaration":
        func = func.parent
    if func is None:
        return False
    name = func.child_by_field_name("name")
    if name is None or not data[name.start_byte : name.end_byte].startswith(b"Example"):
        return False
    # The expected output is the `// Output:` comment and every comment after it.
    return any(
        c.start_byte <= node.start_byte and _GO_OUTPUT.match(data, c.start_byte)
        for c in _captures(_query("go", "(comment) @c"), func, "c")
    )


def _in_text_element(node: Node, data: bytes) -> bool:
    parent = node.parent
    while parent is not None:
        tag = parent.child(0)
        if parent.type == "element" and tag is not None and tag.type == "start_tag":
            name = tag.child_by_field_name("name") or (tag.child(1) if tag.child_count > 1 else None)
            if name is not None and data[name.start_byte : name.end_byte].lower() in _HTML_TEXT_ELEMENTS:
                return True
        parent = parent.parent
    return False


def _attributes(start_tag: Node, data: bytes) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for attr in start_tag.named_children:
        if attr.type != "attribute" or not attr.named_children:
            continue
        name = attr.named_children[0]
        value = attr.named_children[-1] if len(attr.named_children) > 1 else None
        raw = data[value.start_byte : value.end_byte].decode() if value is not None else ""
        attrs[data[name.start_byte : name.end_byte].decode().lower()] = raw.strip("\"'").strip().lower()
    return attrs


def _embedded_language(element: Node, data: bytes) -> str | None:
    """Pick the grammar of a <script> or <style> body, or None when it is data."""
    start = element.child(0)
    attrs = _attributes(start, data) if start is not None else {}
    if element.type == "style_element":
        return _STYLE_LANGS.get(attrs.get("lang", ""))
    if "lang" in attrs:
        return _SCRIPT_LANGS.get(attrs["lang"])
    kind = attrs.get("type", "").split(";")[0].strip()
    if kind in _JS_TYPES:
        return "javascript"
    if kind in ("importmap", "speculationrules") or kind.endswith(("/json", "+json")):
        return "json"
    return None  # a template or other data block


# (literal spans, docstring spans) in absolute byte offsets.
Layout = tuple[list[tuple[int, int]], list[tuple[int, int]]]


def _record_layout(root: Node, base: int, docs: list[Node], layout: Layout) -> None:
    """Record the outermost literal nodes of ``root`` and its docstrings, offset by ``base``."""
    doc_spans = [(n.start_byte, n.end_byte) for n in docs]
    layout[1].extend((base + s, base + e) for s, e in doc_spans)
    stack = [root]
    while stack:
        node = stack.pop()
        # A docstring's blanked interior is not data, so it is compared like code.
        if (node.start_byte, node.end_byte) in doc_spans:
            continue
        holds_doc = any(node.start_byte <= s and e <= node.end_byte for s, e in doc_spans)
        if node.is_named and not holds_doc and _LITERAL_KIND.search(node.type):
            layout[0].append((base + node.start_byte, base + node.end_byte))
        else:
            stack.extend(node.children)


def _collect(
    lang: str,
    data: bytes,
    base: int,
    spans: list[tuple[int, int, bool]],
    fragment: bool = False,
    layout: Layout | None = None,
) -> None:
    """Append (start, end, is_doc) byte spans to blank in ``data``, offset by ``base``.

    With ``layout``, also record the literal and docstring byte spans of every
    tree parsed, for the mechanical comparison.

    A ``fragment`` (a macro body, a recipe line, a template expression) need
    not be a whole program, so its comments are taken even from a tree with
    errors: the lexer still finds them, and skipping would leak them.

    Raises:
        SyntaxError: When ``data`` is not a fragment and the grammar cannot parse it.
    """
    # Hold the tree: a node outlives a dropped tree only as a dangling pointer (a segfault).
    tree = Parser(_language_object(lang)).parse(data)
    root = tree.root_node
    if root.has_error and not fragment:
        raise SyntaxError(f"{lang} parse error at line {_first_error(root).start_point.row + 1}")
    comments, docs = _queries(lang)
    py_blocks = [range(m.start(), m.end()) for m in _PY_SCRIPT_BLOCK.finditer(data)] if lang == "python" else []
    markup = lang in ("html", "svelte")
    for node in _captures(comments, root, "comment"):
        if _kept(lang, node, data, py_blocks) or (markup and _in_text_element(node, data)):
            continue
        # Docker reads `#` as a comment only at the start of a line; elsewhere it is an argument.
        if lang == "dockerfile" and data[data.rfind(b"\n", 0, node.start_byte) + 1 : node.start_byte].strip():
            continue
        spans.append((base + node.start_byte, base + node.end_byte, False))
    doc_nodes = _docstrings(lang, root)
    if layout is not None:
        _record_layout(root, base, doc_nodes, layout)
    for node in doc_nodes:
        # The grammar's content children lie between the delimiters, whatever they are (`~S|...|`).
        content = [c for c in node.children if c.type in _DOC_CONTENT]
        text = data[node.start_byte : node.end_byte]
        quote = _DOC_QUOTE.match(text)
        if content:
            spans.append((base + content[0].start_byte, base + content[-1].end_byte, True))
        elif quote and len(text) >= quote.end() + len(quote.group(1)) and text.endswith(quote.group(1)):
            spans.append((base + node.start_byte + quote.end(), base + node.end_byte - len(quote.group(1)), True))
        elif len(text) > 2:
            raise SyntaxError(f"{lang} docstring delimiters not recognized at line {node.start_point.row + 1}")
    if lang in ("c", "cpp"):
        # The grammar keeps a macro body as raw text, so comments in it need their own parse.
        for arg in _captures(_query(lang, "(preproc_arg) @arg"), root, "arg"):
            arg_text = data[arg.start_byte : arg.end_byte]
            _collect(lang, arg_text, base + arg.start_byte, spans, fragment=True, layout=layout)
    if lang == "make":
        # Outside recipes and define bodies, make ends a line at any unescaped `#`.
        protected = [(n.start_byte, n.end_byte) for n in _captures(_query(lang, "[(recipe_line) (raw_text)] @p"), root, "p")]
        for m in _MAKE_COMMENT.finditer(data):
            if not any(start <= m.start() < end for start, end in protected):
                spans.append((base + m.start(), base + m.end(), False))
        # make hands a recipe line to the shell, so its `#` comments are shell comments.
        for line in _captures(_query(lang, "(recipe_line) @line"), root, "line"):
            text = data[line.start_byte : line.end_byte]
            skip = len(text) - len(text.lstrip(b"@+- \t"))
            _collect("bash", text[skip:], base + line.start_byte + skip, spans, fragment=True, layout=layout)
    if markup:
        for element in _captures(_query(lang, "[(script_element) (style_element)] @el"), root, "el"):
            body = next((c for c in element.children if c.type == "raw_text"), None)
            inner = _embedded_language(element, data)
            if body is not None and inner is not None:
                _collect(inner, data[body.start_byte : body.end_byte], base + body.start_byte, spans, layout=layout)
            elif body is not None and layout is not None:
                layout[0].append((base + body.start_byte, base + body.end_byte))  # a data block
    if lang == "svelte":
        # Template expressions are JS, though a fragment such as `items as item` is not a program.
        for expr in _captures(_query(lang, "(svelte_raw_text) @js"), root, "js"):
            _collect(
                "javascript", data[expr.start_byte : expr.end_byte], base + expr.start_byte, spans, True, layout
            )


@functools.cache
def _query(lang: str, pattern: str) -> Query:
    return Query(_language_object(lang), pattern)


def _first_error(node: Node) -> Node:
    for child in node.children:
        if child.has_error:
            return _first_error(child)
    return node


def _char_index(source: str) -> Callable[[int], int]:
    """Map tree-sitter's UTF-8 byte offsets in ``source`` to str indices."""
    if source.isascii():
        return lambda offset: offset
    widths = (1 if o < 0x80 else 2 if o < 0x800 else 3 if o < 0x10000 else 4 for o in map(ord, source))
    starts = list(itertools.accumulate(widths, initial=0))
    return lambda offset: bisect.bisect_left(starts, offset)


def _blank(source: str, spans: list[tuple[int, int, bool]]) -> str:
    """Blank byte spans of ``source`` to spaces, keeping line breaks."""
    out = list(source)
    to_char = _char_index(source)
    for start, end, is_doc in spans:
        start, end = to_char(start), to_char(end)
        for k in range(start, end):
            ch = source[k]
            # A backslash before a newline continues a single-quoted string.
            if ch in "\r\n" or (is_doc and ch == "\\" and source[k + 1 : k + 2] in ("\r", "\n")):
                continue
            out[k] = " "
    return "".join(out)


def _tree_sitter(lang: str, source: str) -> str:
    spans: list[tuple[int, int, bool]] = []
    _collect(lang, source.encode("utf-8"), 0, spans)
    return _blank(source, spans)


# A tag, a comment, or a script or style body: braces there are not an interpolation.
_VUE_NOT_TEXT = "[(start_tag) (end_tag) (self_closing_tag) (comment) (raw_text)] @x"


def _vue_interpolations(data: bytes, not_text: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return the ``{{ ... }}`` spans that start in template text, scanning left to right."""
    found, pos = [], 0
    while (start := data.find(b"{{", pos)) >= 0:
        if any(s <= start < e for s, e in not_text):
            pos = start + 2
            continue
        end = data.find(b"}}", start + 2)
        if end < 0:
            break
        found.append((start, end + 2))
        pos = end + 2
    return found


def strip_vue(source: str) -> str:
    """Strip a Vue single-file component as HTML, plus comments in ``{{ }}`` JS.

    Vue reads an interpolation up to the first ``}}`` before it looks for tags,
    so ``{{ "<!-- x -->" }}`` holds a string, not a comment. Which braces are
    interpolations depends on where the tags are, and the tags depend on which
    braces are masked, so mask and reparse until the two agree.

    Raises:
        SyntaxError: When they never agree; a guess could blank template text.
    """
    return _blank(source, _vue_spans(source.encode("utf-8")))


def _subtract(spans: list[tuple[int, int]], holes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return ``spans`` with every ``holes`` range cut out."""
    for hole_start, hole_end in holes:
        spans = [
            piece
            for start, end in spans
            for piece in ((start, min(end, hole_start)), (max(start, hole_end), end))
            if piece[0] < piece[1]
        ]
    return spans


def _vue_spans(data: bytes, layout: Layout | None = None) -> list[tuple[int, int, bool]]:
    """Return the blank spans of a Vue component; see ``strip_vue``."""
    parser = Parser(_language_object("html"))
    tree = parser.parse(data)  # held while its nodes are read
    root = tree.root_node
    for _ in range(8):
        not_text = [(n.start_byte, n.end_byte) for n in _captures(_query("html", _VUE_NOT_TEXT), root, "x")]
        interpolations = _vue_interpolations(data, not_text)
        masked = bytearray(data)
        for start, end in interpolations:
            masked[start:end] = bytes(b if b in b"\r\n" else 32 for b in data[start:end])
        tree = parser.parse(bytes(masked))
        root = tree.root_node
        settled = [(n.start_byte, n.end_byte) for n in _captures(_query("html", _VUE_NOT_TEXT), root, "x")]
        if _vue_interpolations(data, settled) == interpolations:
            break
    else:
        raise SyntaxError("vue interpolations and tags do not settle")
    spans: list[tuple[int, int, bool]] = []
    markup: Layout = ([], [])
    _collect("html", bytes(masked), 0, spans, layout=markup)
    if layout is not None:
        # A text node spans the masked interpolations; their JS literals are recorded below.
        layout[0].extend(_subtract(markup[0], interpolations))
        layout[1].extend(markup[1])
    for start, end in interpolations:
        _collect("javascript", data[start + 2 : end - 2], start + 2, spans, fragment=True, layout=layout)
    return spans


def _lines(pattern: str) -> Callable[[str], str]:
    """Strip a line-oriented config format whose comments a regex finds exactly."""
    compiled = re.compile(pattern, re.MULTILINE)

    def strip(source: str) -> str:
        _no_bare_cr(source)
        return compiled.sub(lambda m: " " * len(m.group()), source)

    return strip


_BARE_CR = re.compile(r"\r(?!\n)")


def _no_bare_cr(source: str) -> None:
    """Refuse a bare CR: readers disagree on whether it ends a line, so a comment's end is unknown.

    Raises:
        SyntaxError: When ``source`` holds a CR that is not part of CRLF.
    """
    if _BARE_CR.search(source):
        raise SyntaxError("bare CR line terminator")


def _whole_line_comments(markers: str, bare_cr: bool = False) -> Callable[[str], str]:
    r"""Strip lines that start with one of ``markers`` in a grammarless config format.

    A line after one that ends in an odd number of backslashes continues a
    value (Java properties, git config), so it is data even when it starts
    with a marker. With ``bare_cr``, a bare `\r` also ends a line, as
    ``java.util.Properties.load`` reads it; otherwise a bare `\r` fails the strip.
    """

    def strip(source: str) -> str:
        if not bare_cr:
            _no_bare_cr(source)
        out, continued = [], False
        for line in re.findall(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$", source):
            body = line.rstrip("\r\n")
            if not continued and body.lstrip(" \t\f")[:1] in markers:
                out.append(" " * len(body) + line[len(body) :])
                continue  # a comment line never continues
            out.append(line)
            continued = _CONTINUED.search(body) is not None
        return "".join(out)

    return strip


strip_properties = _whole_line_comments("#!", bare_cr=True)


def _grammar(lang: str) -> Callable[[str], str]:
    return functools.partial(_tree_sitter, lang)


def _suffixes(spec: str, strip: Callable[[str], str]) -> dict[str, Callable[[str], str]]:
    return dict.fromkeys(spec.split(), strip)


HASH_LINES = _whole_line_comments("#")
INI_LINES = _whole_line_comments("#;")
# pip: a `#` at line start or after whitespace starts a comment; `url#egg=` is data.
REQUIREMENTS_LINES = _lines(r"(?:^|(?<=[ \t]))#[^\r\n]*")

LANGUAGES_BY_SUFFIX: dict[str, Callable[[str], str]] = {
    **_suffixes(".py .pyi .pyw", _grammar("python")),
    **_suffixes(".c .h .glsl .vert .frag .hlsl", _grammar("c")),
    **_suffixes(".cc .cpp .cxx .c++ .hpp .hh .hxx .h++ .ino .cu .cuh .metal", _grammar("cpp")),
    **_suffixes(".cs", _grammar("c_sharp")),
    **_suffixes(".java", _grammar("java")),
    **_suffixes(".kt .kts", _grammar("kotlin")),
    **_suffixes(".scala .sc", _grammar("scala")),
    **_suffixes(".swift", _grammar("swift")),
    **_suffixes(".dart", _grammar("dart")),
    **_suffixes(".groovy .gradle", _grammar("groovy")),
    **_suffixes(".go", _grammar("go")),
    **_suffixes(".rs", _grammar("rust")),
    **_suffixes(".zig", _grammar("zig")),
    **_suffixes(".js .jsx .mjs .cjs", _grammar("javascript")),
    **_suffixes(".ts .mts .cts", _grammar("typescript")),
    **_suffixes(".tsx", _grammar("tsx")),
    **_suffixes(".css", _grammar("css")),
    **_suffixes(".scss .less", _grammar("scss")),
    **_suffixes(".json .jsonc .json5", _grammar("json")),
    **_suffixes(".php", _grammar("php")),
    **_suffixes(".sh .bash .zsh .ksh", _grammar("bash")),
    **_suffixes(".mk", _grammar("make")),
    **_suffixes(".dockerfile", _grammar("dockerfile")),
    **_suffixes(".toml", _grammar("toml")),
    **_suffixes(".yaml .yml", _grammar("yaml")),
    **_suffixes(".ini .cfg", INI_LINES),
    **_suffixes(".properties", strip_properties),
    **_suffixes(".conf", HASH_LINES),
    **_suffixes(".rb .rake .gemspec .ru", _grammar("ruby")),
    **_suffixes(".pl .pm .t", _grammar("perl")),
    **_suffixes(".jl", _grammar("julia")),
    **_suffixes(".ex .exs", _grammar("elixir")),
    **_suffixes(".hs", _grammar("haskell")),
    **_suffixes(".ml", _grammar("ocaml")),
    **_suffixes(".mli", _grammar("ocaml_interface")),
    **_suffixes(".fs .fsx", _grammar("fsharp")),
    **_suffixes(".fsi", _grammar("fsharp_signature")),
    **_suffixes(".lisp .lsp .cl", _grammar("commonlisp")),
    **_suffixes(".ps1 .psm1 .psd1", _grammar("powershell")),
    **_suffixes(".lua", _grammar("lua")),
    **_suffixes(".sql", _grammar("sql")),
    **_suffixes(".tf .tfvars .hcl", _grammar("hcl")),
    **_suffixes(".nix", _grammar("nix")),
    **_suffixes(".graphql .gql", _grammar("graphql")),
    **_suffixes(".cmake", _grammar("cmake")),
    **_suffixes(".html .htm", _grammar("html")),
    **_suffixes(".vue", strip_vue),
    **_suffixes(".svelte", _grammar("svelte")),
    **_suffixes(
        ".xml .xhtml .svg .plist .xsd .xsl .xslt .csproj .fsproj .vbproj .props .targets .xaml"
        " .storyboard .xib .config .resx .nuspec",
        _grammar("xml"),
    ),
}
# Files with no suffix, or whose suffix would mislead (CMakeLists.txt is not
# documentation). A dotfiles repo is mostly these.
LANGUAGES_BY_NAME: dict[str, Callable[[str], str]] = {
    **_suffixes("Dockerfile Containerfile", _grammar("dockerfile")),
    **_suffixes("Makefile makefile GNUmakefile", _grammar("make")),
    **_suffixes(
        "Brewfile Gemfile Rakefile Podfile Vagrantfile Guardfile Fastfile Appfile Dangerfile",
        _grammar("ruby"),
    ),
    **_suffixes("CMakeLists.txt", _grammar("cmake")),
    **_suffixes(
        ".envrc .bashrc .bash_profile .bash_aliases .bash_logout .profile .zshrc .zshenv .zprofile"
        " .zlogin .zlogout",
        _grammar("bash"),
    ),
    **_suffixes(".env", _grammar("bash")),  # sourced by shells; quoted values span lines
    **_suffixes(
        ".gitignore .gitattributes .dockerignore .npmignore .prettierignore .eslintignore"
        " .helmignore CODEOWNERS",
        _lines(r"^#[^\r\n]*"),
    ),
    **_suffixes(
        ".editorconfig .gitconfig .gitmodules .npmrc .flake8 .pylintrc .coveragerc",
        INI_LINES,
    ),
    **_suffixes("go.mod go.work", _lines(r"^[ \t]*//[^\r\n]*")),
    **_suffixes("Pipfile", _grammar("toml")),
}
LANGUAGES_BY_GLOB: list[tuple[str, Callable[[str], str]]] = [
    ("requirements*.txt", REQUIREMENTS_LINES),
    ("constraints*.txt", REQUIREMENTS_LINES),
    ("Dockerfile.*", _grammar("dockerfile")),
    ("Containerfile.*", _grammar("dockerfile")),
    (".env.*", _grammar("bash")),
]


# `#!/usr/bin/env -S python3 -u` names python; an executable with no suffix is common.
_SHEBANG = re.compile(r"#![ \t]*(?:\S*/)?(?:env[ \t]+(?:-S[ \t]+)?(?:\S*/)?)?([a-z]+)")
_SHEBANG_LANGUAGES = {
    "sh": "bash", "bash": "bash", "zsh": "bash", "ksh": "bash", "dash": "bash",
    "python": "python", "ruby": "ruby", "perl": "perl", "node": "javascript",
}


def _dispatch(path_name: str, source: str = "") -> tuple[str, Callable[[str], str]] | None:
    """Return (token, stripper) for a path, or None when its language is unknown.

    The token names only the language (``.py``, ``-Makefile``, ``-env``), so a
    mechanical unit label carries no part of the path beyond that.
    """
    path = Path(path_name)
    if path.name in LANGUAGES_BY_NAME:
        return "-" + path.name.lstrip("."), LANGUAGES_BY_NAME[path.name]
    for pattern, strip in LANGUAGES_BY_GLOB:
        if fnmatch.fnmatchcase(path.name, pattern):
            return "-" + pattern.split("*")[0].strip("."), strip
    suffix = path.suffix.lower()
    if suffix in LANGUAGES_BY_SUFFIX:
        return suffix, LANGUAGES_BY_SUFFIX[suffix]
    shebang = _SHEBANG.match(source)
    lang = _SHEBANG_LANGUAGES.get(shebang.group(1)) if shebang else None
    return ("-" + lang, _grammar(lang)) if lang else None


def _language(path_name: str, source: str = "") -> Callable[[str], str] | None:
    """Return the stripper for a path, or None when its language is unknown."""
    found = _dispatch(path_name, source)
    return found[1] if found else None


def validate_strip(path_name: str, source: str, stripped: str) -> str | None:
    """Check that a strip removed only comments and kept every position.

    Every stripper blanks comment characters to spaces in place, so the output
    must be a space-mask of the input: identical length, identical line count,
    and every non-space character unchanged. A stripper that deletes code (a
    misread regex literal, a mis-tracked quote state) violates the mask and is
    caught here rather than reaching the blind reviewer as broken source.

    Args:
        path_name: Path used to pick the language-specific check.
        source: Original file text.
        stripped: Candidate stripped text.

    Returns:
        A one-line reason when the strip is unsafe, or None when it is sound.
    """
    if len(stripped) != len(source):
        return f"length changed ({len(source)} -> {len(stripped)})"
    if stripped.count("\n") != source.count("\n"):
        return "line count changed"
    for index, (before, after) in enumerate(zip(source, stripped)):
        if before != after and after != " ":
            line = source.count("\n", 0, index) + 1
            return f"character rewritten at line {line} (not blanked)"
    if Path(path_name).suffix.lower() == ".py":
        # A 200,000-term expression overflows the compiler's stack; that proves nothing.
        try:
            compile(source, path_name, "exec")
        except (SyntaxError, RecursionError, MemoryError):
            return None  # input was already unparseable; nothing to prove
        try:
            compile(stripped, path_name, "exec")
        except SyntaxError as exc:
            return f"stripped Python no longer parses ({exc.msg})"
        except (RecursionError, MemoryError) as exc:
            return f"stripped Python could not be compiled ({type(exc).__name__})"
    return None


def strip_source(path_name: str, source: str) -> tuple[str, str]:
    """Return (stripped_source, action) for a file by suffix.

    A strip that fails validation degrades to copied-verbatim with the reason
    attached. An honestly-flagged unstripped file costs the blind arm some
    context; a silently mangled one poisons its findings.
    """
    strip = _language(path_name, source)
    if strip is None:
        return source, "copied-verbatim (unknown language)"
    try:
        stripped = strip(source)
    except SyntaxError:
        return source, "copied-verbatim (parse error)"
    reason = validate_strip(path_name, source, stripped)
    if reason is not None:
        return source, f"copied-verbatim (strip validation failed: {reason})"
    return stripped, "stripped"


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout.

    Args:
        repo: Repository root.
        *args: Arguments passed to git.

    Returns:
        The command's stdout.

    Raises:
        SystemExit: If git fails, with its stderr as the message. A traceback
            would bury the actual cause (a bad --base, usually).
    """
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def process_file(rel: str, data: bytes) -> tuple[str | None, str]:
    """Return (stripped_text_or_None, action) for raw file content."""
    if Path(rel).suffix.lower() in DOC_SUFFIXES and _language(rel) is None:
        return None, "omitted-doc"
    if _is_binary(data):
        return None, "skipped-binary"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "skipped-undecodable"
    return strip_source(rel, text)


_PHYSICAL_LINE = re.compile(r"[^\n]*\n|[^\n]+\Z")


def _physical_lines(text: str) -> list[str]:
    """Split at newlines only, as git does; ``str.splitlines`` also splits at form feed."""
    return _PHYSICAL_LINE.findall(text)


def _unified_diff(base: str, head: str, rel: str) -> str:
    """Render one file's unified diff with git-compatible line termination.

    ``difflib.unified_diff`` emits a body line without a trailing newline when
    the source file had none, and it never emits git's "\\ No newline at end
    of file" marker. Joining those chunks glues the next line (and the next
    file's header) onto the previous one, producing a patch git refuses.

    Args:
        base: Stripped base text.
        head: Stripped head text.
        rel: Repository-relative path used in the headers.

    Returns:
        A diff chunk that is empty when the two sides match, and otherwise ends
        in a newline.
    """
    lines = list(
        difflib.unified_diff(
            _physical_lines(base),
            _physical_lines(head),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )
    rendered: list[str] = []
    for line in lines:
        if line.endswith("\n"):
            rendered.append(line)
        else:
            rendered.append(line + "\n\\ No newline at end of file\n")
    return "".join(rendered)


def _assert_diff_applies(repo: Path, diff_path: Path) -> None:
    """Warn when the emitted patch is not one git can parse.

    The stripped diff is the primary artifact handed to the blind reviewer. A
    malformed one is not visibly broken, so check that git can parse it rather
    than trusting the generator.

    Args:
        repo: Repository the patch was generated against.
        diff_path: Path to the written patch.
    """
    if not diff_path.read_text(encoding="utf-8").strip():
        return
    # --numstat parses the patch without consulting the worktree. `apply
    # --check` would fail legitimately here: the patch is between *stripped*
    # texts, which by construction do not match the files on disk.
    result = subprocess.run(
        ["git", "-C", str(repo), "apply", "--numstat", str(diff_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"warning: {diff_path} is not a well-formed patch "
            f"({result.stderr.strip().splitlines()[:1]})",
            file=sys.stderr,
        )


def _changed_files(repo: Path, base: str) -> list[tuple[str, str]]:
    """List (base_path, head_path) changed between ``base`` and the worktree.

    The two paths differ only for a rename, whose base must be read from the
    original path. Untracked files are included.
    """
    # Include untracked files so both review passes receive the same changes.
    # -z: without it git quotes unusual names ("caf\303\251.py"), which then match no file.
    fields = _git(repo, "diff", "--name-status", "-M", "-z", base).split("\0")
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(fields) and fields[i]:
        if fields[i].startswith(("R", "C")):  # C appears under diff.renames=copies
            pairs.append((fields[i + 1], fields[i + 2]))
            i += 3
        else:
            pairs.append((fields[i + 1], fields[i + 1]))
            i += 2
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    pairs += [(rel, rel) for rel in untracked if rel]
    return list(dict.fromkeys(pairs))


def _base_and_head(
    repo: Path, base: str, base_rel: str, rel: str
) -> tuple[bytes | None, bytes | None]:
    """Return the bytes of ``base_rel`` at ``base`` and of ``rel`` in the worktree.

    Either is None when absent.
    """
    try:
        base_data: bytes | None = subprocess.run(
            ["git", "-C", str(repo), "show", f"{base}:{base_rel}"],
            capture_output=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        base_data = None  # added file
    head_path = repo / rel
    # A path under a symlinked directory is absent to git; following the link
    # would read outside the repo. ``repo`` is already resolved.
    if head_path.parent.resolve() != head_path.parent:
        return base_data, None
    # Git stores a symlink as its target path. Following it would copy the file
    # it points at (say ~/.ssh/id_rsa) into review input sent to a model.
    if head_path.is_symlink():
        return base_data, os.readlink(head_path).encode()
    return base_data, head_path.read_bytes() if head_path.is_file() else None


_NO_CONTENT = "skipped (no file content, such as a submodule)"


def _clear(path: Path) -> None:
    """Remove a generated file or tree; a symlink is removed, never followed."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _write(out: Path, dest: Path, text: str) -> None:
    """Write a generated file under ``out`` without following a symlink out of it.

    Raises:
        SystemExit: When a directory on the way to ``dest`` leads outside
            ``out``; writing there could overwrite a source file.
    """
    existing = dest.parent
    while not existing.exists() and existing != out:
        existing = existing.parent
    resolved = existing.resolve()
    if resolved != out and out not in resolved.parents:
        raise SystemExit(f"{dest.parent} leads outside --out {out}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    dest.write_text(text, encoding="utf-8")


def _repo_and_out(args: argparse.Namespace) -> tuple[Path, Path]:
    """Resolve --repo and --out, refusing an --out inside the repo.

    Raises:
        SystemExit: When one directory holds the other. Inside the repo, the
            manifest (which maps unit labels to paths) would be reviewed next
            run; above it, cleaning --out/head or --out/units could delete it.
    """
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    if out == repo or repo in out.parents or out in repo.parents:
        raise SystemExit(f"--out {out} and --repo {repo} must not contain each other")
    return repo, out


def cmd_diff(args: argparse.Namespace) -> int:
    repo, out = _repo_and_out(args)
    # A tree from an earlier run can hold files this change no longer touches.
    for generated in ("base", "head"):
        _clear(out / generated)
    changed = _changed_files(repo, args.base)
    manifest: list[dict[str, str]] = []
    diff_chunks: list[str] = []
    for base_rel, rel in changed:
        base_data, head_data = _base_and_head(repo, args.base, base_rel, rel)

        entry = {"path": rel, "action": "" if (base_data, head_data) != (None, None) else _NO_CONTENT}
        if base_rel != rel:
            entry["base_path"] = base_rel
        stripped_base = stripped_head = None
        for label, data, tree in (
            ("base", base_data, "base"),
            ("head", head_data, "head"),
        ):
            if data is None:
                continue
            stripped, action = process_file(rel, data)
            # A failure on either side must stay visible; a clean head must not
            # relabel a base that was copied verbatim.
            if entry["action"] in ("", "stripped"):
                entry["action"] = action
            if stripped is None:
                continue
            _write(out, out / tree / rel, stripped)
            if label == "base":
                stripped_base = stripped
            else:
                stripped_head = stripped
        manifest.append(entry)
        if entry["action"].startswith(("omitted", "skipped")):
            continue
        diff_chunks.append(_unified_diff(stripped_base or "", stripped_head or "", rel))

    out.mkdir(parents=True, exist_ok=True)
    _write(out, out / "stripped.diff", "".join(diff_chunks))
    _assert_diff_applies(repo, out / "stripped.diff")
    _write(out, out / "manifest.json", json.dumps({"repo": str(repo), "base": args.base, "files": manifest}, indent=2))
    print(f"stripped {len(changed)} changed file(s) into {out}")
    print(f"review targets: {out}/head and {out}/stripped.diff")
    return 0


# Leading whitespace is syntax here, so a re-indent is a code change.
INDENT_SENSITIVE_LANGUAGES = {"python", "yaml", "haskell", "fsharp", "fsharp_signature", "make"}
# A line holding only a blanked docstring or one of its quote delimiters.
_BLANK_STRING = re.compile(r"""[rRbBuU]{0,2}(\"\"\"|'''|"|')(?:\s*\1)?""")
# Node kinds whose text is data, so whitespace inside them counts.
_LITERAL_KIND = re.compile(
    r"string|heredoc|regex|sigil|str_lit|char_literal|rune_literal|character_literal|quote_scalar|block_scalar"
    r"|plain_scalar|jsx_text|^literal$|quoted_argument|bracket_argument"  # YAML, JSX, SQL, CMake values
    r"|attribute_value|^text$|^CharData$"  # markup text: `<pre>` and CSS can make its whitespace render
)
# A backslash-escaped space is part of a word (shell `foo\ bar`), so it never starts a run.
_WHITESPACE = re.compile(r"(?<!\\)\s+")
_TRAILING = re.compile(r"(?<!\\)\s+\Z")
_CONTINUED = re.compile(r"(?<!\\)(?:\\\\)*\\\r?$")


def _grammar_name(rel: str, text: str) -> str | None:
    """Return the grammar a path (or its shebang) strips with, or None."""
    found = _dispatch(rel, text)
    strip = found[1] if found else None
    if isinstance(strip, functools.partial) and strip.func is _tree_sitter:
        return strip.args[0]
    return None


def _layout(rel: str, text: str) -> tuple[set[int], list[tuple[int, int]]] | None:
    """Return (docstring rows, literal spans as str indices) of a stripped text.

    The stripped text still parses, because only comment and docstring
    interiors were blanked, so the stripper's own parses (embedded scripts,
    template expressions, macro bodies) are repeated to find literals. Without
    a grammar (a line-oriented config format, whose comments are whole lines)
    the result is None, and each line is compared exactly.
    """
    found = _dispatch(rel, text)
    strip = found[1] if found else None
    data = text.encode("utf-8")
    layout: Layout = ([], [])
    try:
        if isinstance(strip, functools.partial) and strip.func is _tree_sitter:
            _collect(strip.args[0], data, 0, [], layout=layout)
        elif strip is strip_vue:
            _vue_spans(data, layout)
        else:
            return None
    except SyntaxError:
        return set(), []
    literals, docs = layout
    rows = {row for s, e in docs for row in range(data.count(b"\n", 0, s), data.count(b"\n", 0, e) + 1)}
    merged: list[tuple[int, int]] = []
    for start, end in sorted(literals):  # an embedded parse may sit inside an outer literal
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    to_char = _char_index(text)
    return rows, [(to_char(s), to_char(e)) for s, e in merged]


def _compare_key(line: str, parts: list[tuple[int, int]]) -> str:
    """Collapse whitespace runs outside the literal ``parts`` of ``line``, keep it inside."""
    pieces, pos = [], 0
    for start, end in [*parts, (len(line), len(line))]:
        pieces += [_WHITESPACE.sub(" ", line[pos:start]), line[start:end]]
        pos = end
    key = "".join(pieces)
    if not parts or parts[0][0] > 0:
        key = key.lstrip()
    if not parts or parts[-1][1] < len(line):
        key = _TRAILING.sub("", key)  # `foo\ ` at a line end keeps its escaped space
    return key


def _code_lines(
    text: str,
    indent_sensitive: bool,
    layout: tuple[set[int], list[tuple[int, int]]] | None = (set(), []),
    inline_comments: bool = False,
    source: str | None = None,
) -> list[tuple[int, str, str]]:
    """Return (line_number, compare_key, display) for each line that holds code.

    Blank lines (including comment-only lines, which the stripper blanked) and
    docstring rows holding only blanked quotes are dropped. Outside literals
    the key collapses each run of whitespace to one space (deleting it would
    equate ``rm -rf /tmp`` and ``rm -rf / tmp``); inside ``literals``,
    whitespace and blank lines are data and count. Raw leading indentation is
    kept when it is syntax. With no ``layout`` (no grammar), each line is
    compared exactly, apart from trailing whitespace.
    """
    lines = text.split("\n")
    # A blank line after a `\`-continued line ends the command (or value), so it counts.
    ends_continued = [False] + [_CONTINUED.search(line) is not None for line in lines[:-1]]
    if layout is None:
        # These formats comment only whole lines, so trailing spaces are value data,
        # except where a trailing comment was blanked (requirements files). A blank
        # line can be data too (an INI multi-line value) when it was not a comment.
        originals = source.split("\n") if source is not None else None
        return [
            (n, *(2 * [line.rstrip() if inline_comments else line.rstrip("\r")]))
            for n, line in enumerate(lines, 1)
            if line.strip()
            or ends_continued[n - 1]
            or (n < len(lines) and (not line.rstrip("\r") or (originals is not None and originals[n - 1] == line)))
        ]
    doc_rows, literals = layout
    rows = []
    offset = first = 0
    for number, line in enumerate(lines, 1):
        start, end = offset, offset + len(line)
        offset = end + 1
        while first < len(literals) and literals[first][1] <= start:
            first += 1
        parts = []
        for s, e in literals[first:]:
            if s >= end:
                break
            parts.append((max(s, start) - start, min(e, end) - start))
        body = line.strip()
        if not body:
            if parts:  # a blank or whitespace-only line inside a multi-line string is data
                rows.append((number, _compare_key(line, parts), line))
            elif ends_continued[number - 1]:
                rows.append((number, "", ""))
            continue
        if number - 1 in doc_rows and _BLANK_STRING.fullmatch(body):
            continue
        key = _compare_key(line, parts)
        if indent_sensitive and not (parts and parts[0][0] == 0):
            key = line[: len(line) - len(line.lstrip())] + key
        ends_in_literal = parts and parts[-1][1] == len(line)
        rows.append((number, key, line if ends_in_literal else _TRAILING.sub("", line)))
    return rows


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def _changed_ranges(old: list[str], new: list[str]) -> list[tuple[int, int, int, int]]:
    """Return the (i1, i2, j1, j2) slices of ``old`` and ``new`` that differ.

    git's histogram diff is used because ``difflib.SequenceMatcher`` is
    quadratic on repeated lines: a lockfile bump took minutes.

    Raises:
        SystemExit: If git cannot compare the two line lists.
    """
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp, "a"), Path(tmp, "b")
        a.write_text("".join(f"{line}\n" for line in old), encoding="utf-8")
        b.write_text("".join(f"{line}\n" for line in new), encoding="utf-8")
        result = subprocess.run(
            ["git", "diff", "--no-index", "--no-ext-diff", "--no-textconv", "--no-color",
             "--histogram", "-U0", str(a), str(b)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    if result.returncode not in (0, 1):
        raise SystemExit(f"git diff --no-index: {result.stderr.strip()}")
    ranges = []
    for m in _HUNK_HEADER.finditer(result.stdout):
        old_count = 1 if m[2] is None else int(m[2])
        new_count = 1 if m[4] is None else int(m[4])
        # A count of 0 means the start names the line before the insertion point.
        i1 = int(m[1]) - (1 if old_count else 0)
        j1 = int(m[3]) - (1 if new_count else 0)
        ranges.append((i1, i1 + old_count, j1, j1 + new_count))
    return ranges


def mechanical_hunks(rel: str, base: str, head: str, sources: tuple[str, str] | None = None) -> str:
    """Render only the changed code lines between two stripped texts.

    Args:
        rel: Repository-relative path, used to pick indentation handling.
        base: Stripped base text ("" for an added file).
        head: Stripped head text ("" for a deleted file).
        sources: The unstripped (base, head) texts. Without a grammar, a
            whitespace-only line equal to its source line is data, not a
            blanked comment; without ``sources`` it is dropped.

    Returns:
        ``-N|line`` and ``+N|line`` rows with original line numbers, groups
        separated by ``@@``; empty when no code line changed.
    """
    sensitive = _grammar_name(rel, head or base) in INDENT_SENSITIVE_LANGUAGES
    found = _dispatch(rel, head or base)
    inline = found is not None and found[1] is REQUIREMENTS_LINES
    base_source, head_source = sources or (None, None)
    old = _code_lines(base, sensitive, _layout(rel, base), inline, base_source)
    new = _code_lines(head, sensitive, _layout(rel, head), inline, head_source)
    groups = []
    for i1, i2, j1, j2 in _changed_ranges([k for _, k, _ in old], [k for _, k, _ in new]):
        rows = [f"-{n}|{d}" for n, _, d in old[i1:i2]]
        rows += [f"+{n}|{d}" for n, _, d in new[j1:j2]]
        groups.append("\n".join(rows))
    return "\n@@\n".join(groups) + "\n" if groups else ""


def cmd_mechanical(args: argparse.Namespace) -> int:
    """Write one changed-lines unit per file for context-free review.

    Reviewers receive a unit file and nothing else, so the unit carries an
    anonymous label instead of the path (paths state intent). The label-to-path
    map lives only in manifest.json, which is for the dispatcher, never a
    reviewer. Files that cannot be stripped are omitted, not copied verbatim.
    """
    repo, out = _repo_and_out(args)
    units = out / "units"
    # Output of an earlier run describes another revision. mechanical_review.py
    # globs units/, so a leftover unit would be reviewed as if it were current.
    for generated in ("units", "payloads", "results"):
        _clear(out / generated)
    units.mkdir(parents=True)
    manifest: list[dict[str, str]] = []
    unit_count = 0
    for base_rel, rel in _changed_files(repo, args.base):
        entry = {"path": rel, "action": ""}
        if base_rel != rel:
            entry["base_path"] = base_rel
        manifest.append(entry)
        pair = _base_and_head(repo, args.base, base_rel, rel)
        if pair == (None, None):
            entry["action"] = _NO_CONTENT
            continue
        texts, sources = [], []
        for data in pair:
            if data is None:
                texts.append("")
                sources.append("")
                continue
            stripped, action = process_file(rel, data)
            if stripped is None or action != "stripped":
                entry["action"] = action if stripped is None else f"omitted ({action})"
                break
            texts.append(stripped)
            sources.append(data.decode("utf-8"))
        else:
            hunks = mechanical_hunks(rel, *texts, sources=(sources[0], sources[1]))
            if not hunks:
                entry["action"] = "no-code-change"
                continue
            unit_count += 1
            found = _dispatch(rel, texts[-1] or texts[0])
            label = f"f{unit_count:02d}{found[0] if found else ''}"
            entry.update(action="stripped", unit=label)
            _write(out, units / f"{label}.diff", f"file {label}\n{hunks}")
    _write(
        out,
        out / "manifest.json",
        json.dumps({"repo": str(repo), "base": args.base, "mode": "mechanical", "files": manifest}, indent=2),
    )
    print(f"wrote {unit_count} unit(s) from {len(manifest)} changed file(s) into {units}")
    return 0


def cmd_files(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    manifest: list[dict[str, str]] = []
    for p in args.paths:
        src = Path(p)
        # A relative path may still climb out of --out with `..`; keep every
        # written file inside the output root.
        rel = src.name if src.is_absolute() else os.path.normpath(str(src))
        if rel.startswith("..") or os.path.isabs(rel):
            rel = src.name
        stripped, action = process_file(rel, src.read_bytes())
        manifest.append({"path": rel, "action": action})
        if stripped is not None:
            _write(out, out / rel, stripped)
    out.mkdir(parents=True, exist_ok=True)
    _write(out, out / "manifest.json", json.dumps({"files": manifest}, indent=2))
    print(f"stripped {len(args.paths)} file(s) into {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested subcommand.

    Args:
        argv: Argument list, defaulting to ``sys.argv[1:]``.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="strip base+head of a git diff")
    d.add_argument("--repo", default=".")
    d.add_argument("--base", default="HEAD")
    d.add_argument("--out", required=True)
    d.set_defaults(func=cmd_diff)
    f = sub.add_parser("files", help="strip individual files")
    f.add_argument("--out", required=True)
    f.add_argument("paths", nargs="+")
    f.set_defaults(func=cmd_files)
    m = sub.add_parser("mechanical", help="changed code lines only, one unit per file")
    m.add_argument("--repo", default=".")
    m.add_argument("--base", default="HEAD")
    m.add_argument("--out", required=True)
    m.set_defaults(func=cmd_mechanical)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
