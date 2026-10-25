#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""strip_context.py: PoC comment/docstring/doc stripper for blind code review.

Produces a scratch workspace whose files have identical line and column
numbers to the originals, with all comments, docstrings, and documentation
removed. Comment characters are replaced with spaces (never deleted) so
findings in the stripped copy cite real source locations directly.

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

from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import functools
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc", ".mdx"}
BACKSLASH = re.compile(r"\\[\s\S]")
EOL = re.compile(r"(?=\n)|\Z")
Closer = re.Pattern[str] | Callable[[re.Match[str]], re.Pattern[str]]
Guard = Callable[[str, int, list[str]], bool]


class Rule(NamedTuple):
    """One lexical construct: where it opens, where it closes, and what it is.

    ``kind`` decides what happens to the text: "comment" is blanked, "doc"
    keeps its delimiters and blanks its contents, "string" and "keep" (code
    that looks like a comment, such as ``//go:build``) are left alone,
    "regex" is a JS-style regex literal, and "heredoc" keeps a body that
    starts on the next line.
    """

    kind: str
    open: re.Pattern[str]
    close: Closer = EOL
    skip: re.Pattern[str] | None = None  # escape sequences inside a string
    nested: re.Pattern[str] | None = None  # opener that nests a comment
    multiline: bool = True  # False: a newline ends an unterminated string
    interp: tuple[tuple[str, str], ...] = ()  # (opener, closer) of code inside the string
    guard: Guard | None = None


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.MULTILINE)


def _comment(open_: str, close: str | Closer | None = None, nested: bool = False) -> Rule:
    end = EOL if close is None else _rx(close) if isinstance(close, str) else close
    return Rule("comment", _rx(open_), end, nested=_rx(open_) if nested else None)


def _string(
    open_: str,
    close: str | Closer | None = None,
    skip: re.Pattern[str] | str | None = BACKSLASH,
    multiline: bool = True,
    interp: tuple[tuple[str, str], ...] = (),
    guard: Guard | None = None,
    kind: str = "string",
) -> Rule:
    end = _rx(open_) if close is None else _rx(close) if isinstance(close, str) else close
    esc = _rx(skip) if isinstance(skip, str) else skip
    return Rule(kind, _rx(open_), end, esc, None, multiline, interp, guard)


def _keep(pattern: str) -> Rule:
    return Rule("keep", _rx(pattern))


_PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}


def _delimited(group: int) -> Closer:
    """Close a literal with the delimiter it opened with, or its bracket pair."""

    def close(m: re.Match[str]) -> re.Pattern[str]:
        delim = m.group(group)
        return re.compile(re.escape(delim if len(delim) > 1 else _PAIRS.get(delim, delim)))

    return close


def _long_bracket(m: re.Match[str]) -> re.Pattern[str]:
    """Close Lua and CMake ``[==[`` with ``]==]``."""
    return re.compile(r"\]" + m.group(1) + r"\]")


def _heredoc(open_: str, name: int, indent: int | None = None, tail: str = r"[ \t]*$") -> Rule:
    """Build a heredoc rule whose body ends at a line holding the delimiter.

    Args:
        open_: Opener regex.
        name: Group holding the delimiter word.
        indent: Group that, when non-empty, allows an indented closer; None
            always allows one.
        tail: What may follow the delimiter on its line.
    """

    def close(m: re.Match[str]) -> re.Pattern[str]:
        lead = r"[ \t]*" if indent is None or m.group(indent) else ""
        return re.compile(rf"^{lead}{re.escape(m.group(name))}{tail}", re.MULTILINE)

    return Rule("heredoc", _rx(open_), close)


# No `<`: in JSX, `</a>` is a closing tag, not a regex after `<`.
_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%~^>")
_REGEX_KEYWORDS = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "throw",
        "case",
        "do",
        "else",
        "yield",
        "await",
        "and",
        "or",
        "not",
        "if",
        "elsif",
        "unless",
        "when",
        "while",
        "until",
        "split",
        "grep",
    }
)


def _regex_allowed(source: str, i: int, out: list[str]) -> bool:
    """Report whether a ``/`` at ``i`` may open a regex literal.

    A regex may follow an operator, a delimiter, a keyword, or the start of
    input, but not a value. ``out`` already has comments blanked, so a
    comment cannot influence the decision.
    """
    j = i - 1
    while j >= 0 and out[j] in " \t\r\n":
        j -= 1
    if j < 0 or out[j] in _REGEX_PRECEDERS:
        return True
    if out[j] == ")":
        # `if (ok) /re/` starts a statement; `(a + b) / c` divides.
        depth = 0
        while j >= 0:
            depth += {")": 1, "(": -1}.get(out[j], 0)
            if depth == 0:
                break
            j -= 1
        j -= 1
        while j >= 0 and out[j] in " \t\r\n":
            j -= 1
        word = _word_before(out, j)
        # shortcut: a ( or ) inside a string literal miscounts the match; fix by tracking tokens in the scan if it shows up.
        return word in ("if", "while", "for", "with") and out[j - len(word) : j - len(word) + 1] != ["."]
    if out[j].isalnum() or out[j] in "_$":
        return _word_before(out, j) in _REGEX_KEYWORDS
    return False


def _word_before(out: list[str], j: int) -> str:
    """Return the identifier that ends at ``out[j]``."""
    k = j
    while k >= 0 and (out[k].isalnum() or out[k] in "_$"):
        k -= 1
    return "".join(out[k + 1 : j + 1])


def _ruby_regex_allowed(source: str, i: int, out: list[str]) -> bool:
    """Ruby ends a statement at a newline, so a line-leading ``/`` opens a regex."""
    j = i - 1
    while j >= 0 and out[j] in " \t":
        j -= 1
    return j < 0 or out[j] in "\r\n" or _regex_allowed(source, i, out)


def _scan_regex(source: str, start: int) -> int:
    """Measure a regex literal beginning at ``start``.

    Args:
        source: Full source text.
        start: Index of the opening ``/``.

    Returns:
        The literal's length in characters including flags, or 0 when the text
        does not terminate as a regex on this line.
    """
    i, n = start + 1, len(source)
    in_class = False
    while i < n:
        ch = source[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":
            return 0
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "/":
            i += 1
            while i < n and (source[i].isalpha() or source[i] == "_"):
                i += 1
            return i - start
        i += 1
    return 0


def _not_digit_separator(source: str, i: int, out: list[str]) -> bool:
    """Reject the ``'`` in C++14 ``1'000'000``; accept ``u8'a'``."""
    j = i
    while j > 0 and (source[j - 1].isalnum() or source[j - 1] in "_'."):
        j -= 1
    return not source[j:i][:1].isdigit()


def _yaml_value_start(source: str, i: int, out: list[str]) -> bool:
    """A YAML quote opens a scalar only where a value starts, not in ``don't``."""
    j = i - 1
    while j >= 0 and source[j] in " \t":
        j -= 1
    return j < 0 or source[j] in "\n:-[{,?"


_JULIA_DEF = re.compile(
    r"\s*(?:@\w+\s+)*(?:function|macro|struct|mutable\s+struct|abstract\s+type"
    r"|primitive\s+type|module|baremodule|const|[A-Za-z_]\w*(?:\{[^}\n]*\})?\([^)\n]*\)\s*=)"
)
_JULIA_STRING = re.compile(r'"""[\s\S]*?"""|"(?:[^"\\]|\\[\s\S])*"')


def _julia_doc(source: str, i: int, out: list[str]) -> bool:
    """A Julia docstring starts a line and is followed by a definition."""
    if source[source.rfind("\n", 0, i) + 1 : i].strip():
        return False
    m = _JULIA_STRING.match(source, i)
    return m is not None and _JULIA_DEF.match(source, m.end()) is not None


def _graphql_description(source: str, i: int, out: list[str]) -> bool:
    """A GraphQL string is a description unless it is a value."""
    j = i - 1
    while j >= 0 and source[j] in " \t\r\n":
        j -= 1
    return j < 0 or source[j] not in ':=[,"'


def _blank(source: str, out: list[str], start: int, end: int, keep_continuation: bool = False) -> None:
    """Blank ``source[start:end]`` in ``out``, keeping line breaks."""
    for k in range(start, end):
        ch = source[k]
        if ch in "\r\n" or (keep_continuation and ch == "\\" and source[k + 1 : k + 2] in "\r\n"):
            continue
        out[k] = " "


def _closer(rule: Rule, m: re.Match[str]) -> re.Pattern[str]:
    return rule.close if isinstance(rule.close, re.Pattern) else rule.close(m)


def _comment_end(source: str, rule: Rule, m: re.Match[str]) -> int:
    close = _closer(rule, m)
    if rule.nested is None:
        c = close.search(source, m.end())
        return c.end() if c else len(source)
    depth, j = 1, m.end()
    while depth:
        c = close.search(source, j)
        if c is None:
            return len(source)
        o = rule.nested.search(source, j, c.start())
        if o is not None:
            depth, j = depth + 1, o.end()
        else:
            depth, j = depth - 1, c.end()
    return j


def _string_end(
    source: str, out: list[str], rule: Rule, m: re.Match[str], rules: Sequence[Rule]
) -> tuple[int, int | None]:
    """Return (end of the literal, start of its closer or None if unterminated)."""
    close = _closer(rule, m)
    j, n = m.end(), len(source)
    while j < n:
        # Interpolation first: Swift's `\(` would otherwise read as an escape.
        opener = next(((op, cl) for op, cl in rule.interp if source.startswith(op, j)), None)
        if opener is not None:
            j = _scan_code(source, out, j + len(opener[0]), rules, close=opener[1])
            continue
        if rule.skip is not None:
            s = rule.skip.match(source, j)
            if s and s.end() > j:
                j = s.end()
                continue
        c = close.match(source, j)
        if c:
            return c.end(), j
        if not rule.multiline and source[j] == "\n":
            return j, None
        j += 1
    return n, None


def _scan_code(source: str, out: list[str], i: int, rules: Sequence[Rule], close: str = "") -> int:
    """Blank comments in ``out`` from ``i``; return where scanning stopped.

    With ``close`` set (``}`` or ``)``), the scan is inside an interpolation
    such as ``${...}`` or ``$(...)`` and returns just after its closer.
    """
    n = len(source)
    nest = {"}": "{", ")": "("}.get(close, "")
    found: list[re.Match[str] | None | bool] = [False] * len(rules)
    pending: list[re.Pattern[str]] = []
    depth = 0
    while i < n:
        start, choice = n, None
        for k, rule in enumerate(rules):
            m = found[k]
            if m is False or (isinstance(m, re.Match) and m.start() < i):
                m = found[k] = rule.open.search(source, i)
            if isinstance(m, re.Match) and m.start() < start:
                start = m.start()
        for k, rule in enumerate(rules):
            m = found[k]
            if not isinstance(m, re.Match) or m.start() != start:
                continue
            if rule.guard is None or rule.guard(source, start, out):
                choice = (rule, m)
                break
        gap_end = start if choice else min(start + 1, n)
        if close or pending:
            resumed = None
            for k in range(i, gap_end):
                ch = source[k]
                if close and ch == nest:
                    depth += 1
                elif close and ch == close:
                    if depth == 0:
                        return k + 1
                    depth -= 1
                if pending and ch == "\n":
                    resumed = k + 1
                    for closer in pending:
                        c = closer.search(source, resumed)
                        resumed = c.end() if c else n
                    pending.clear()
                    break
            if resumed is not None:
                i = resumed
                continue
        if choice is None:
            i = gap_end
            continue
        rule, m = choice
        if rule.kind == "keep":
            i = m.end()
        elif rule.kind == "heredoc":
            # An opener with no closing line is a shift operator or a typo.
            if _closer(rule, m).search(source, m.end()):
                pending.append(_closer(rule, m))
                i = m.end()
            else:
                i = start + 1
        elif rule.kind == "regex":
            i = start + (_scan_regex(source, start) or 1)
        elif rule.kind == "body":
            # Code quoted as a literal, such as a PL/pgSQL `AS $$ ... $$` body.
            c = _closer(rule, m).search(source, m.end())
            end = c.start() if c else n
            _scan_code(source[:end], out, m.end(), rules)
            i = c.end() if c else n
        elif rule.kind == "comment":
            i = _comment_end(source, rule, m)
            _blank(source, out, start, i)
        else:
            i, body_end = _string_end(source, out, rule, m, rules)
            # An unterminated doc may be a misread; blanking to EOF would delete code.
            if rule.kind == "doc" and body_end is not None:
                _blank(source, out, m.end(), body_end, keep_continuation=True)
        if i <= start:
            i = start + 1
    return n


def _scan(source: str, rules: Sequence[Rule]) -> str:
    """Strip comments and doc literals from ``source`` under ``rules``."""
    out = list(source)
    _scan_code(source, out, 0, rules)
    return "".join(out)


# Shared rule groups. Order matters only between rules that open at the same
# position: the earlier rule wins, so `"""` precedes `"` and `///` directives
# precede `//`.
SHEBANG = _keep(r"\A#!.*")
BLOCK = _comment(r"/\*", r"\*/")
NESTED_BLOCK = _comment(r"/\*", r"\*/", nested=True)
LINE = _comment("//")
URL_SAFE_LINE = _comment(r"(?<![A-Za-z]:)//")  # `https://x` in JSX text or CSS url()
DQ = _string('"', multiline=False)
SQ = _string("'", multiline=False)
REGEX = Rule("regex", _rx(r"/(?![/*])"), guard=_regex_allowed)
CODE_ESCAPE = _keep(r"\\[\s\S]")
# A `'` followed by a name and no closing `'` is a lifetime, symbol, or type
# variable (`'static`, `'sym`, `'a list`), not a char literal.
CHAR = _string(r"(?<![\w'])'(?![A-Za-z_](?!'))", "'", multiline=False)
SHELL_HASH = _comment(r"(?<![^\s;&|()])#")
WORD_HASH = _comment(r"(?<!\S)#")
LINE_HASH = _comment(r"^[ \t]*#")
SH_HEREDOC = _heredoc(r"(?<!<)<<(-?)[ \t]*([\"']?)\\?([A-Za-z_]\w*)\2", name=3, indent=1)
CHAR_LITERAL = _keep(r"(?<![\w?!])\?\\?[^\s]")  # Ruby, Elixir, Elisp `?#`
DOLLAR_BRACE = (("${", "}"),)
HASH_BRACE = (("#{", "}"),)
SHELL_SUBST = (("$(", ")"), ("${", "}"))

C = [
    BLOCK,
    LINE,
    _string(
        r'(?<!\w)(?:u8|[uUL])?R"([^()\\\s]{0,16})\(',
        lambda m: re.compile(r"\)" + re.escape(m.group(1)) + '"'),
        skip=None,
    ),
    DQ,
    _string("'", multiline=False, guard=_not_digit_separator),
]
CSHARP = [
    BLOCK,
    LINE,
    _string(r'\$*("{3,})', lambda m: re.compile(m.group(1)), skip=None),
    _string(r'(?:\$@|@\$|@)"', '"', skip='""'),
    DQ,
    SQ,
]
JAVA = [BLOCK, LINE, _string('"""'), DQ, SQ]
KOTLIN = [
    NESTED_BLOCK,
    LINE,
    _string('"""', skip=None, interp=DOLLAR_BRACE),
    _string('"', multiline=False, interp=DOLLAR_BRACE),
    SQ,
]
SCALA = [
    NESTED_BLOCK,
    LINE,
    _string('"""', skip=None, interp=DOLLAR_BRACE),
    _string('"', multiline=False, interp=DOLLAR_BRACE),
    CHAR,
]
SWIFT_INTERP = (("\\(", ")"),)
SWIFT = [
    NESTED_BLOCK,
    LINE,
    _string(r'(#+)("""|")', lambda m: re.compile(re.escape(m.group(2) + m.group(1))), skip=None),
    _string('"""', interp=SWIFT_INTERP),
    _string('"', multiline=False, interp=SWIFT_INTERP),
]
DART = [
    NESTED_BLOCK,
    LINE,
    _string(r"(?<![\w$])r'''", "'''", skip=None),
    _string(r'(?<![\w$])r"""', '"""', skip=None),
    _string("'''", interp=DOLLAR_BRACE),
    _string('"""', interp=DOLLAR_BRACE),
    _string(r"(?<![\w$])r'", "'", skip=None, multiline=False),
    _string(r'(?<![\w$])r"', '"', skip=None, multiline=False),
    _string("'", multiline=False, interp=DOLLAR_BRACE),
    _string('"', multiline=False, interp=DOLLAR_BRACE),
]
GROOVY = [
    SHEBANG,
    BLOCK,
    LINE,
    _string(r"\$/", r"/\$", skip=r"\$[$/]"),
    REGEX,
    _string("'''"),
    _string('"""', interp=DOLLAR_BRACE),
    SQ,
    _string('"', multiline=False, interp=DOLLAR_BRACE),
]
GO = [
    _keep(r"^//(?:go:|line |export |extern )[^\n]*"),
    _keep(r"^// \+build[^\n]*"),
    BLOCK,
    LINE,
    _string("`", skip=None),
    DQ,
    SQ,
]
RUST = [
    _string(r'#!?\[doc\s*=\s*"', '"', kind="doc"),
    NESTED_BLOCK,
    LINE,
    _string(r'(?<!\w)b?r(#*)"', lambda m: re.compile('"' + m.group(1)), skip=None),
    _string('"'),
    _string(r"'(?![A-Za-z_](?!'))", "'", multiline=False),
]
JS = [
    SHEBANG,
    _keep(r"^[ \t]*///[ \t]*<(?:reference|amd-module|amd-dependency)\b[^\n]*"),
    BLOCK,
    URL_SAFE_LINE,
    REGEX,
    _string("`", interp=DOLLAR_BRACE),
    DQ,
    SQ,
]
CSS = [BLOCK, DQ, SQ]
SCSS = [BLOCK, URL_SAFE_LINE, DQ, SQ]
JSONC = [BLOCK, LINE, DQ, SQ]  # JSON5 allows single-quoted strings
ZIG = [_keep(r"\\\\[^\n]*"), LINE, DQ, SQ]
PHP = [
    _string(r"\A(?!<\?)", r"<\?(?:php\b|=)?", skip=None),  # HTML before the first tag
    _string(r"\?>", r"<\?(?:php\b|=)?", skip=None),  # HTML between tags is output
    _keep(r"#\["),  # PHP 8 attribute
    BLOCK,
    _comment(r"//|#", r"(?=\n|\?>)|\Z"),
    _heredoc(r"<<<[ \t]*([\"']?)([A-Za-z_]\w*)\1", name=2, tail=r"\b"),
    _string('"', interp=(("{$", "}"), ("${", "}"))),
    _string("'", skip=r"\\[\\']"),
]
SHELL = [
    SHEBANG,
    CODE_ESCAPE,
    SH_HEREDOC,
    SHELL_HASH,
    _string(r"\$'", "'"),
    _string("'", skip=None),
    _string('"', interp=SHELL_SUBST),
    _string("`"),
]
FISH = [SHEBANG, CODE_ESCAPE, SHELL_HASH, _string("'", skip=r"\\['\\]"), _string('"')]
MAKE = [
    CODE_ESCAPE,
    _comment(r"(?<![^\s;&|()@+-])#"),  # `@`, `-`, `+` prefix a recipe line
    _string("'", skip=None, multiline=False),
    _string('"', multiline=False),
]
JUST = [
    SHEBANG,
    _keep(r"^[ \t]+#!.*"),  # a shebang recipe line selects the interpreter
    CODE_ESCAPE,
    SH_HEREDOC,
    SHELL_HASH,
    _string('"""'),
    _string("'''", skip=None),
    _string("```", skip=None),
    _string("'", skip=None),
    _string('"', interp=SHELL_SUBST),
    _string("`"),
]
DOCKER = [
    _keep(r"\A(?:[ \t]*#[ \t]*(?:syntax|escape|check)[ \t]*=[^\n]*\n)+"),  # parser directives
    SH_HEREDOC,
    LINE_HASH,
]
LINE_HASH_ONLY = [LINE_HASH]
INI = [_comment(r"^[ \t]*[#;]")]
PROPERTIES = [_comment(r"^[ \t]*[#!]")]
CONF = [WORD_HASH, _string("'", skip=None, multiline=False), _string('"', multiline=False)]
REQUIREMENTS = [WORD_HASH]
TOML = [
    _comment("#"),
    _string('"""'),
    _string("'''", skip=None),
    _string('"', multiline=False),
    _string("'", skip=None, multiline=False),
]
YAML = [
    WORD_HASH,
    _string("'", skip="''", guard=_yaml_value_start),
    _string('"', guard=_yaml_value_start),
]
RUBY = [
    SHEBANG,
    _keep(
        r"^#[ \t]*(?:frozen_string_literal|encoding|coding|warn_indent|warn_past_scope"
        r"|shareable_constant_value)[ \t]*:[^\n]*"
    ),
    _keep(r"^__END__\n[\s\S]*"),  # data section
    _comment(r"^=begin\b", r"^=end\b[^\n]*|\Z"),
    CHAR_LITERAL,
    _heredoc(r"<<([~-]?)([\"'`]?)([A-Z_][A-Za-z0-9_]*)\2", name=3, indent=1),
    # Ruby regex literals may span lines (`/x`) and interpolate.
    _string(r"/(?![/*])", r"/[a-z]*", interp=HASH_BRACE, guard=_ruby_regex_allowed),
    _string(r"%[qQwWiIrsx]?([^\w\s])", _delimited(1), interp=HASH_BRACE, guard=_ruby_regex_allowed),
    _comment("#"),
    _string('"', interp=HASH_BRACE),
    _string("'", skip=r"\\[\\']"),
    _string("`", interp=HASH_BRACE),
]
PERL = [
    SHEBANG,
    _keep(r"^__(?:END|DATA)__\b[\s\S]*"),
    _comment(r"^=[a-zA-Z]\w*", r"^=cut\b[^\n]*|\Z"),  # POD
    _heredoc(r"<<(~?)([\"']?)([A-Za-z_]\w*)\2", name=3, indent=1),
    _string(r"(?<![\w$@%])(?:qq|qw|qx|qr|q|m)\s*([^\w\s=,;)])", _delimited(1)),
    _string(
        r"(?<![\w$@%])(?:s|tr|y)\s*([^\w\s=,;)(\[{<])",
        lambda m: re.compile(
            f"{re.escape(m.group(1))}(?:[^{re.escape(m.group(1))}\\\\]|\\\\.)*{re.escape(m.group(1))}"
        ),
    ),
    REGEX,
    _comment(r"(?<!\$)#"),
    _string('"'),
    _string("'", skip=r"\\[\\']"),
    _string("`"),
]
R = [
    _comment("#"),
    _string(
        r"(?<![\w.])[rR]([\"'])(-*)([\[({])",
        lambda m: re.compile(re.escape(_PAIRS[m.group(3)] + m.group(2) + m.group(1))),
        skip=None,
    ),
    _string('"'),
    _string("'"),
    _string("`"),
]
JULIA = [
    _comment("#=", "=#", nested=True),
    _string('"""', kind="doc", guard=_julia_doc),
    _string('"', kind="doc", guard=_julia_doc),
    _comment("#"),
    _string('"""'),
    _string('"'),
    _string(r"(?<![\w')\]}.])'", "'", multiline=False),  # `x'` is a transpose
    _string("`"),
]
ELIXIR = [
    CHAR_LITERAL,
    _string(r'@(?:moduledoc|doc|typedoc)\s+(?:~[sS])?"""', '"""', kind="doc"),
    _string(r'@(?:moduledoc|doc|typedoc)\s+(?:~[sS])?"', '"', kind="doc"),
    _string(r"~[a-zA-Z]+(\"\"\"|'''|[/|\"'(\[{<])", _delimited(1), interp=HASH_BRACE),
    _comment("#"),
    _string('"""', interp=HASH_BRACE),
    _string("'''", interp=HASH_BRACE),
    _string('"', interp=HASH_BRACE),
    _string("'", interp=HASH_BRACE),
]
HASKELL = [
    _keep(r"\{-#[\s\S]*?#-\}"),  # pragmas change compilation
    _comment(r"\{-", r"-\}", nested=True),
    _comment(r"--+(?![!#$%&*+./<=>?@\\^|~:])"),  # `-->` is an operator
    _string('"'),
    CHAR,
]
OCAML = [
    _comment(r"\(\*(?!\))", r"\*\)", nested=True),  # `( * )` is an operator
    _string(r"\{([a-z_]*)\|", lambda m: re.compile(re.escape("|" + m.group(1) + "}")), skip=None),
    _string('"'),
    CHAR,
]
FSHARP = [
    _comment(r"\(\*(?!\))", r"\*\)", nested=True),
    LINE,
    _string('"""', skip=None),
    _string('@"', '"', skip='""'),
    _string('"'),
    CHAR,
]
ERLANG = [_keep(r"\$\\?[\s\S]"), _comment("%"), _string('"'), _string("'")]
CLOJURE = [
    CODE_ESCAPE,  # char literals such as \; and \"
    _string(
        r'\((?:defn-?|defmacro|defmulti|defprotocol|ns)\s+(?:\^\S+\s+)*[^\s()\[\]{}";]+\s+"',
        '"',
        kind="doc",
    ),
    _comment(";"),
    _string('"'),
]
LISP = [
    CODE_ESCAPE,
    CHAR_LITERAL,
    _string(
        r'\((?:defun|defmacro|cl-defun|cl-defmacro|defsubst|defgeneric)\s+\S+\s+\([^()]*\)\s+"',
        '"',
        kind="doc",
    ),
    _comment(r"#\|", r"\|#", nested=True),
    _comment(";"),
    _string('"'),
]
POWERSHELL = [
    _keep(r"^(?i:#requires)\b[^\n]*"),
    _comment("<#", "#>"),  # comment-based help
    _keep(r"`[\s\S]"),
    _string(r'@"[ \t]*$', r'^"@', skip=None),
    _string(r"@'[ \t]*$", r"^'@", skip=None),
    _comment(r"(?<![^\s;|&({])#"),
    _string('"', skip=r'`[\s\S]|""'),
    _string("'", skip="''"),
]
LUA = [
    SHEBANG,
    _comment(r"--\[(=*)\[", _long_bracket),
    _comment("--"),
    _string(r"\[(=*)\[", _long_bracket, skip=None),
    DQ,
    SQ,
]
# PostgreSQL identifiers may hold `$`, so `a$b$` is not a quote.
DOLLAR_QUOTE = r"(?<![\w$])\$(?:[A-Za-z_]\w*)?\$"
_ROUTINE_BODY_PRECEDER = re.compile(r"(?<!\w)(?:AS|DO(?:\s+LANGUAGE\s+\w+)?)\s*\Z", re.IGNORECASE)


def _same_text(m: re.Match[str]) -> re.Pattern[str]:
    """Close a ``$tag$`` quote with the same tag."""
    return re.compile(re.escape(m.group(0)))


def _dollar_quote_closed(source: str, i: int, out: list[str]) -> bool:
    """Open a dollar quote only if its tag recurs; an unterminated one would hide the rest."""
    tag = re.compile(DOLLAR_QUOTE).match(source, i)
    return tag is not None and source.find(tag.group(0), tag.end()) >= 0


def _sql_routine_body(source: str, i: int, out: list[str]) -> bool:
    """A dollar quote after ``AS`` or ``DO`` holds a routine body, not data."""
    preceder = _ROUTINE_BODY_PRECEDER.search("".join(out[max(0, i - 200) : i]))
    return preceder is not None and _dollar_quote_closed(source, i, out)


SQL = [
    _comment(r"/\*", r"\*/", nested=True),
    _comment("--"),
    _string(r"(?<!\w)[eE]'", "'", skip=r"\\[\s\S]|''"),
    _string("'", skip="''"),
    # `AS $$` and `DO $$` quote a routine body, which is code; any other
    # dollar-quoted text is string data.
    Rule("body", _rx(DOLLAR_QUOTE), _same_text, guard=_sql_routine_body),
    _string(DOLLAR_QUOTE, _same_text, skip=None, guard=_dollar_quote_closed),
    _string('"', skip='""'),
    _string("`", skip="``"),
]
HCL = [
    _comment("#"),
    BLOCK,
    LINE,
    _heredoc(r"<<(-?)([A-Za-z_]\w*)", name=2),
    _string('"', interp=(("${", "}"), ("%{", "}")), multiline=False),
]
NIX = [
    WORD_HASH,
    BLOCK,
    # `''` ends an indented string unless followed by `'`, `$`, or `\`.
    _string("''", r"''(?![$'\\])", skip=r"''[$']|''\\[\s\S]", interp=DOLLAR_BRACE),
    _string('"', interp=DOLLAR_BRACE),
]
GRAPHQL = [
    _comment("#"),
    _string('"""', skip=r'\\"""', kind="doc", guard=_graphql_description),
    _string('"', multiline=False, kind="doc", guard=_graphql_description),
    _string('"""', skip=r'\\"""'),
    DQ,
]
CMAKE = [
    CODE_ESCAPE,  # `\"` in an unquoted argument is not a quote
    _comment(r"#\[(=*)\[", _long_bracket),
    _comment("#"),
    _string(r"\[(=*)\[", _long_bracket, skip=None),
    _string('"'),
]

_TAG_NAME = re.compile(r"<([A-Za-z][\w:.-]*)")
_SCRIPT_TYPES = {
    "module",
    "text/javascript",
    "application/javascript",
    "text/babel",
    "text/typescript",
    "application/json",
    "application/ld+json",
    "importmap",
}


def _embedded_rules(name: str, tag: str) -> Sequence[Rule] | None:
    """Pick the rules for a ``<script>`` or ``<style>`` body, or None to keep it."""
    lang_m = re.search(r"""\blang\s*=\s*["']?([\w-]+)""", tag, re.IGNORECASE)
    lang = lang_m.group(1).lower() if lang_m else ""
    if name == "style":
        if lang in ("scss", "less", "sass"):
            return SCSS
        return CSS if lang in ("", "css", "postcss") else None
    type_m = re.search(r"""\btype\s*=\s*["']?([^"'\s>]+)""", tag, re.IGNORECASE)
    kind = type_m.group(1).lower() if type_m else ""
    if lang in ("", "js", "javascript", "jsx", "ts", "typescript", "tsx") and (
        not kind or kind in _SCRIPT_TYPES
    ):
        return JS
    return None


def _markup(source: str, raw_text: bool) -> str:
    """Strip ``<!-- -->`` comments, keeping quoted attributes and CDATA.

    With ``raw_text`` (HTML, Vue, Svelte, SVG), ``<script>`` and ``<style>``
    bodies are code: an HTML comment marker in them is not a comment, and
    their own comments are stripped with the JS or CSS rules.
    """
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        if source.startswith("<!--", i):
            end = source.find("-->", i + 4)
            end = n if end < 0 else end + 3
            _blank(source, out, i, end)
            i = end
        elif source.startswith("<![CDATA[", i):
            end = source.find("]]>", i + 9)
            i = n if end < 0 else end + 3
        elif source[i] == "<" and i + 1 < n and (source[i + 1].isalpha() or source[i + 1] in "/?!"):
            # The validator cannot tell blanked attribute text from a stripped
            # comment, so quoted attribute values must be skipped whole.
            j, quote = i + 1, ""
            while j < n and (quote or source[j] != ">"):
                if quote:
                    quote = "" if source[j] == quote else quote
                elif source[j] in "\"'":
                    quote = source[j]
                j += 1
            tag = source[i : j + 1]
            i = j + 1
            name_m = _TAG_NAME.match(tag)
            name = name_m.group(1).lower() if name_m else ""
            if raw_text and name in ("script", "style") and not tag.endswith("/>"):
                close = re.compile(rf"</{name}\s*>", re.IGNORECASE).search(source, i)
                end = close.start() if close else n
                rules = _embedded_rules(name, tag)
                if rules is not None:
                    out[i:end] = _scan(source[i:end], rules)
                i = end
        else:
            i += 1
    return "".join(out)


def strip_xml(source: str) -> str:
    """Strip XML comments."""
    return _markup(source, raw_text=False)


def strip_html(source: str) -> str:
    """Strip HTML comments and the comments in embedded scripts and styles."""
    return _markup(source, raw_text=True)


_PY_CODING = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
# PEP 723 inline script metadata: dependencies, so code, not commentary.
_PY_SCRIPT_BLOCK = re.compile(r"^# /// [a-zA-Z0-9-]+$\s(?:^#(?:| .*)$\s)+^# ///$", re.MULTILINE)


def strip_python(source: str) -> str:
    """Strip comments and docstrings from Python source, preserving positions.

    Comments become spaces, except a shebang, a PEP 263 coding line, and PEP
    723 script metadata. A string expression statement (a docstring or a
    bare string constant) keeps its prefix and quotes and loses its content,
    so the result is a space mask that still parses. Raises on tokenize or
    parse errors; the caller copies verbatim.
    """
    lines = source.splitlines(keepends=True)
    kept_rows: set[int] = set()
    if lines and lines[0].startswith("#!"):
        kept_rows.add(1)
    kept_rows.update(row for row in (1, 2) if row <= len(lines) and _PY_CODING.match(lines[row - 1]))
    for m in _PY_SCRIPT_BLOCK.finditer(source):
        first = source.count("\n", 0, m.start()) + 1
        kept_rows.update(range(first, first + m.group().count("\n") + 1))

    def blank_span(srow: int, scol: int, erow: int, ecol: int) -> None:
        for row in range(srow, erow + 1):
            line = lines[row - 1]
            chars = list(line)
            start = scol if row == srow else 0
            end = ecol if row == erow else len(line)
            # A backslash before a newline continues a single-quoted string.
            _blank(line, chars, start, min(end, len(line)), keep_continuation=True)
            lines[row - 1] = "".join(chars)

    def char_col(row: int, byte_col: int) -> int:
        # ast columns are UTF-8 byte offsets; tokenize and slicing use characters.
        return len(lines[row - 1].encode("utf-8")[:byte_col].decode("utf-8"))

    # A string expression statement's syntactic position, not the previous
    # token, tells it apart from a dict value or annotation, and covers
    # `def f(): """doc"""; return 1`.
    docs = [
        (
            (node.lineno, char_col(node.lineno, node.col_offset)),
            (node.end_lineno, char_col(node.end_lineno, node.end_col_offset)),
        )
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, (str, bytes))
        and node.end_lineno is not None
        and node.end_col_offset is not None
    ]
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and tok.start[0] not in kept_rows:
            blank_span(*tok.start, *tok.end)
        elif tok.type == tokenize.STRING and any(s <= tok.start and tok.end <= e for s, e in docs):
            text = tok.string
            prefix = len(text) - len(text.lstrip("rRbBuU"))
            quote = 3 if text[prefix : prefix + 3] in ('"""', "'''") else 1
            (srow, scol), (erow, ecol) = tok.start, tok.end
            blank_span(srow, scol + prefix + quote, erow, ecol - quote)
    return "".join(lines)


_YAML_BLOCK_HEADER = re.compile(r"(?:^|[:-]\s)\s*(?:[!&]\S*\s+)*[|>][1-9+-]{0,2}$")


def strip_yaml(source: str) -> str:
    """Strip YAML #-comments but keep block scalar bodies, which are data.

    In ``key: |`` followed by ``  # deny``, the ``#`` line is string content.
    Bodies are masked before the scan, so a quote inside one cannot shift
    quote state for the lines after it, and are restored afterwards.
    """
    lines = source.splitlines(keepends=True)
    body: set[int] = set()
    i = 0
    while i < len(lines):
        header = _scan(lines[i], YAML).rstrip()
        i += 1
        if lines[i - 1].lstrip().startswith("#") or not _YAML_BLOCK_HEADER.search(header):
            continue
        parent = len(header) - len(header.lstrip(" "))
        # shortcut: auto-detects content indentation and ignores an explicit
        # indicator such as `|2`; parse the indicator if such files appear.
        start = i
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i == len(lines):
            break
        indent = len(lines[i]) - len(lines[i].lstrip(" "))
        if indent <= parent:
            i = start
            continue
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" " * indent)):
            i += 1
        body.update(range(start, i))
    masked = "".join(
        "".join(c if c in "\r\n" else " " for c in line) if n in body else line
        for n, line in enumerate(lines)
    )
    stripped = _scan(masked, YAML).splitlines(keepends=True)
    return "".join(lines[n] if n in body else line for n, line in enumerate(stripped))


def _rules(rules: Sequence[Rule]) -> Callable[[str], str]:
    return functools.partial(_scan, rules=rules)


def _suffixes(spec: str, strip: Callable[[str], str]) -> dict[str, Callable[[str], str]]:
    return dict.fromkeys(spec.split(), strip)


LANGUAGES_BY_SUFFIX: dict[str, Callable[[str], str]] = {
    **_suffixes(".py .pyi .pyw", strip_python),
    **_suffixes(
        ".c .h .cc .cpp .cxx .c++ .hpp .hh .hxx .h++ .ino .m .mm .cu .cuh .glsl .vert .frag"
        " .hlsl .metal .proto .sol",
        _rules(C),
    ),
    **_suffixes(".cs", _rules(CSHARP)),
    **_suffixes(".java", _rules(JAVA)),
    **_suffixes(".kt .kts", _rules(KOTLIN)),
    **_suffixes(".scala .sc", _rules(SCALA)),
    **_suffixes(".swift", _rules(SWIFT)),
    **_suffixes(".dart", _rules(DART)),
    **_suffixes(".groovy .gradle", _rules(GROOVY)),
    **_suffixes(".go", _rules(GO)),
    **_suffixes(".rs", _rules(RUST)),
    **_suffixes(".js .jsx .mjs .cjs .ts .tsx .mts .cts", _rules(JS)),
    **_suffixes(".css", _rules(CSS)),
    **_suffixes(".scss .sass .less", _rules(SCSS)),
    **_suffixes(".json .jsonc .json5", _rules(JSONC)),
    **_suffixes(".zig", _rules(ZIG)),
    **_suffixes(".php", _rules(PHP)),
    **_suffixes(".sh .bash .zsh .ksh", _rules(SHELL)),
    **_suffixes(".fish", _rules(FISH)),
    **_suffixes(".mk", _rules(MAKE)),
    **_suffixes(".dockerfile", _rules(DOCKER)),
    **_suffixes(".toml", _rules(TOML)),
    **_suffixes(".yaml .yml", strip_yaml),
    **_suffixes(".ini .cfg", _rules(INI)),
    **_suffixes(".properties", _rules(PROPERTIES)),
    **_suffixes(".conf", _rules(CONF)),
    **_suffixes(".rb .rake .gemspec .ru", _rules(RUBY)),
    **_suffixes(".pl .pm", _rules(PERL)),
    **_suffixes(".r", _rules(R)),
    **_suffixes(".jl", _rules(JULIA)),
    **_suffixes(".ex .exs", _rules(ELIXIR)),
    **_suffixes(".hs", _rules(HASKELL)),
    **_suffixes(".ml .mli", _rules(OCAML)),
    **_suffixes(".fs .fsi .fsx", _rules(FSHARP)),
    **_suffixes(".erl .hrl", _rules(ERLANG)),
    **_suffixes(".clj .cljs .cljc .edn", _rules(CLOJURE)),
    **_suffixes(".el .lisp", _rules(LISP)),
    **_suffixes(".ps1 .psm1 .psd1", _rules(POWERSHELL)),
    **_suffixes(".lua", _rules(LUA)),
    **_suffixes(".sql", _rules(SQL)),
    **_suffixes(".tf .tfvars .hcl", _rules(HCL)),
    **_suffixes(".nix", _rules(NIX)),
    **_suffixes(".graphql .gql", _rules(GRAPHQL)),
    **_suffixes(".cmake", _rules(CMAKE)),
    **_suffixes(".html .htm .xhtml .vue .svelte .svg", strip_html),
    **_suffixes(
        ".xml .plist .xsd .xsl .xslt .csproj .fsproj .vbproj .props .targets .xaml"
        " .storyboard .xib",
        strip_xml,
    ),
}
# Files with no suffix, or whose suffix would mislead (CMakeLists.txt is not
# documentation). A dotfiles repo is mostly these.
LANGUAGES_BY_NAME: dict[str, Callable[[str], str]] = {
    **_suffixes("Dockerfile Containerfile", _rules(DOCKER)),
    **_suffixes("Makefile makefile GNUmakefile", _rules(MAKE)),
    **_suffixes("Justfile justfile .justfile", _rules(JUST)),
    **_suffixes(
        "Brewfile Gemfile Rakefile Podfile Vagrantfile Guardfile Fastfile Appfile Dangerfile",
        _rules(RUBY),
    ),
    **_suffixes("CMakeLists.txt", _rules(CMAKE)),
    **_suffixes(
        ".envrc .env .bashrc .bash_profile .bash_aliases .bash_logout .profile .zshrc"
        " .zshenv .zprofile .zlogin .zlogout",
        _rules(SHELL),
    ),
    **_suffixes(
        ".gitignore .gitattributes .dockerignore .npmignore .prettierignore .eslintignore"
        " .helmignore CODEOWNERS",
        _rules(LINE_HASH_ONLY),
    ),
    **_suffixes(
        ".editorconfig .gitconfig .gitmodules .npmrc .flake8 .pylintrc .coveragerc",
        _rules(INI),
    ),
    **_suffixes("go.mod go.work", _rules(GO)),
    **_suffixes("Pipfile", _rules(TOML)),
}
LANGUAGES_BY_GLOB: list[tuple[str, Callable[[str], str]]] = [
    ("requirements*.txt", _rules(REQUIREMENTS)),
    ("constraints*.txt", _rules(REQUIREMENTS)),
    ("Dockerfile.*", _rules(DOCKER)),
    ("Containerfile.*", _rules(DOCKER)),
    (".env.*", _rules(SHELL)),
]


def _language(path_name: str) -> Callable[[str], str] | None:
    """Return the stripper for a path, or None when its language is unknown."""
    path = Path(path_name)
    if path.name in LANGUAGES_BY_NAME:
        return LANGUAGES_BY_NAME[path.name]
    for pattern, strip in LANGUAGES_BY_GLOB:
        if fnmatch.fnmatchcase(path.name, pattern):
            return strip
    return LANGUAGES_BY_SUFFIX.get(path.suffix.lower())


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
        try:
            compile(source, path_name, "exec")
        except SyntaxError:
            return None  # input was already unparseable; nothing to prove
        try:
            compile(stripped, path_name, "exec")
        except SyntaxError as exc:
            return f"stripped Python no longer parses ({exc.msg})"
    return None


def strip_source(path_name: str, source: str) -> tuple[str, str]:
    """Return (stripped_source, action) for a file by suffix.

    A strip that fails validation degrades to copied-verbatim with the reason
    attached. An honestly-flagged unstripped file costs the blind arm some
    context; a silently mangled one poisons its findings.
    """
    strip = _language(path_name)
    if strip is None:
        return source, "copied-verbatim (unknown language)"
    try:
        stripped = strip(source)
    except (tokenize.TokenError, IndentationError, SyntaxError):
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
            base.splitlines(keepends=True),
            head.splitlines(keepends=True),
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


def cmd_diff(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    changed = _changed_files(repo, args.base)
    manifest: list[dict[str, str]] = []
    diff_chunks: list[str] = []
    for base_rel, rel in changed:
        base_data, head_data = _base_and_head(repo, args.base, base_rel, rel)

        entry = {"path": rel, "action": ""}
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
            dest = out / tree / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(stripped, encoding="utf-8")
            if label == "base":
                stripped_base = stripped
            else:
                stripped_head = stripped
        manifest.append(entry)
        if entry["action"].startswith(("omitted", "skipped")):
            continue
        diff_chunks.append(_unified_diff(stripped_base or "", stripped_head or "", rel))

    out.mkdir(parents=True, exist_ok=True)
    (out / "stripped.diff").write_text("".join(diff_chunks), encoding="utf-8")
    _assert_diff_applies(repo, out / "stripped.diff")
    (out / "manifest.json").write_text(
        json.dumps({"repo": str(repo), "base": args.base, "files": manifest}, indent=2),
        encoding="utf-8",
    )
    print(f"stripped {len(changed)} changed file(s) into {out}")
    print(f"review targets: {out}/head and {out}/stripped.diff")
    return 0


# Leading whitespace is syntax here, so a re-indent is a code change.
INDENT_SENSITIVE_SUFFIXES = {".py", ".pyi", ".pyw", ".yaml", ".yml", ".hs", ".fs", ".fsx", ".mk"}
INDENT_SENSITIVE_STEMS = {"Makefile", "makefile", "GNUmakefile"}
# A line holding only a blanked docstring or one of its quote delimiters.
_BLANK_STRING = re.compile(r"""[rRbBuU]{0,2}(\"\"\"|'''|"|')(?:\s*\1)?""")


def _code_lines(text: str, indent_sensitive: bool) -> list[tuple[int, str, str]]:
    """Return (line_number, compare_key, display) for each line that holds code.

    Blank lines (including comment-only lines, which the stripper blanked) and
    lines holding only a blanked docstring or its quotes are dropped. The key collapses each run of
    whitespace to one space (deleting it would equate ``rm -rf /tmp`` and
    ``rm -rf / tmp``) and keeps raw leading indentation when it is syntax.
    """
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        body = line.strip()
        if not body or _BLANK_STRING.fullmatch(body):
            continue
        key = " ".join(body.split())
        if indent_sensitive:
            key = line[: len(line) - len(line.lstrip())] + key
        rows.append((number, key, line.rstrip()))
    return rows


def mechanical_hunks(rel: str, base: str, head: str) -> str:
    """Render only the changed code lines between two stripped texts.

    Args:
        rel: Repository-relative path, used to pick indentation handling.
        base: Stripped base text ("" for an added file).
        head: Stripped head text ("" for a deleted file).

    Returns:
        ``-N|line`` and ``+N|line`` rows with original line numbers, groups
        separated by ``@@``; empty when no code line changed.
    """
    path = Path(rel)
    sensitive = (
        path.suffix.lower() in INDENT_SENSITIVE_SUFFIXES or path.name in INDENT_SENSITIVE_STEMS
    )
    old = _code_lines(base, sensitive)
    new = _code_lines(head, sensitive)
    matcher = difflib.SequenceMatcher(
        None, [k for _, k, _ in old], [k for _, k, _ in new], autojunk=False
    )
    groups = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
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
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    units = out / "units"
    # Output of an earlier run describes another revision. mechanical_review.py
    # globs units/, so a leftover unit would be reviewed as if it were current.
    for generated in ("units", "payloads", "results"):
        shutil.rmtree(out / generated, ignore_errors=True)
    units.mkdir(parents=True)
    manifest: list[dict[str, str]] = []
    unit_count = 0
    for base_rel, rel in _changed_files(repo, args.base):
        entry = {"path": rel, "action": ""}
        if base_rel != rel:
            entry["base_path"] = base_rel
        manifest.append(entry)
        texts = []
        for data in _base_and_head(repo, args.base, base_rel, rel):
            if data is None:
                texts.append("")
                continue
            stripped, action = process_file(rel, data)
            if stripped is None or action != "stripped":
                entry["action"] = action if stripped is None else f"omitted ({action})"
                break
            texts.append(stripped)
        else:
            hunks = mechanical_hunks(rel, *texts)
            if not hunks:
                entry["action"] = "no-code-change"
                continue
            unit_count += 1
            # The suffix (or a suffixless name such as Makefile) only names the language.
            kind = Path(rel).suffix.lower() or "-" + Path(rel).name.lstrip(".")
            label = f"f{unit_count:02d}{kind}"
            entry.update(action="stripped", unit=label)
            (units / f"{label}.diff").write_text(f"file {label}\n{hunks}", encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(
            {"repo": str(repo), "base": args.base, "mode": "mechanical", "files": manifest},
            indent=2,
        ),
        encoding="utf-8",
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
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(stripped, encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps({"files": manifest}, indent=2), encoding="utf-8"
    )
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
