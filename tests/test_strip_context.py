#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Unit tests for the blind-review context stripper.

Both failure directions are silent and both defeat the skill: stripping too
much hands the blind reviewer mangled source, so its findings are noise;
stripping too little leaks the comments the blind arm exists to be blind to.
Neither is visible in the output, so every supported language is pinned here.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills/blind-review/scripts/strip_context.py"


def load_script() -> ModuleType:
    """Load the stripper as a module despite its non-importable filename.

    Returns:
        The imported module.
    """
    loader = SourceFileLoader("strip_context", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


strip_context = load_script()


class PositionContractTest(unittest.TestCase):
    """Every strip must be a space-mask of its input."""

    def assert_masked(self, name: str, source: str) -> str:
        """Strip a source and assert positions survived.

        Args:
            name: File name used for language dispatch.
            source: Source text to strip.

        Returns:
            The stripped text.
        """
        stripped, action = strip_context.strip_source(name, source)
        self.assertEqual(action, "stripped", f"{name} was not stripped: {action}")
        self.assertEqual(len(stripped), len(source), "byte count changed")
        self.assertEqual(stripped.count("\n"), source.count("\n"), "line count changed")
        for before, after in zip(source, stripped):
            if before != after:
                self.assertEqual(after, " ", "a character was rewritten, not blanked")
        return stripped


class PythonStripTest(PositionContractTest):
    """Python uses tokenize, so strings must never be mistaken for comments."""

    def test_hash_inside_string_survives(self) -> None:
        """A `#` in a string literal is not a comment."""
        out = self.assert_masked("a.py", 's = "# not a comment"  # real\n')
        self.assertIn('"# not a comment"', out)
        self.assertNotIn("real", out)

    def test_hash_inside_triple_quoted_string_survives(self) -> None:
        """Triple-quoted strings that are not docstrings are data."""
        src = 'x = """\n# inside\n"""\n# gone\n'
        out = self.assert_masked("a.py", src)
        self.assertIn("# inside", out)
        self.assertNotIn("gone", out)

    def test_fstring_and_raw_string_survive(self) -> None:
        """Prefixed strings are strings."""
        out = self.assert_masked("a.py", 'a = f"{x}#y"\nb = r"\\#z"\n# bye\n')
        self.assertIn("#y", out)
        self.assertIn("#z", out)
        self.assertNotIn("bye", out)

    def test_docstrings_are_removed(self) -> None:
        """Module, class, and function docstrings all carry claims to hide."""
        src = '"""Mod."""\n\n\nclass C:\n    """Cls."""\n\n    def m(self):\n        """Fn."""\n        return 1\n'
        out = self.assert_masked("a.py", src)
        for claim in ("Mod.", "Cls.", "Fn."):
            self.assertNotIn(claim, out)
        self.assertIn("return 1", out)

    def test_stripped_python_still_compiles(self) -> None:
        """The blind reviewer must receive parseable source."""
        src = '"""Doc."""\n\n\ndef f(x):\n    """Inner."""\n    return x + 1  # add\n'
        compile(self.assert_masked("a.py", src), "a.py", "exec")

    def test_docstring_in_single_line_suite_is_removed(self) -> None:
        """A docstring after `def f():` on the same line is still a docstring."""
        src = 'def value(): """always safe"""; return 1\n'
        out = self.assert_masked("a.py", src)
        self.assertNotIn("always safe", out)
        self.assertIn("return 1", out)
        compile(out, "a.py", "exec")

    def test_string_after_colon_in_an_expression_survives(self) -> None:
        """Dict values, annotations, and lambda bodies are data, not docstrings."""
        src = 'd = {"k": "v"}\nx: "int" = 1\nf = lambda: "w"\n'
        out = self.assert_masked("a.py", src)
        for literal in ('"v"', '"int"', '"w"'):
            self.assertIn(literal, out)


class SlashStripTest(PositionContractTest):
    """C-family stripping must survive regex literals and template strings."""

    def test_regex_literal_is_not_a_comment_opener(self) -> None:
        """A regex body must survive; only the trailing comment goes."""
        out = self.assert_masked("a.js", "const re = /ab+/;\n// gone\n")
        self.assertIn("/ab+/", out)
        self.assertNotIn("gone", out)

    def test_regex_with_escaped_slashes_survives(self) -> None:
        """The already-working escaped form must not regress."""
        out = self.assert_masked("a.js", "const re = /foo\\/\\/bar/;\n")
        self.assertIn("foo\\/\\/bar", out)

    def test_regex_character_class_with_slash_survives(self) -> None:
        """A `/` inside `[...]` does not close the literal."""
        out = self.assert_masked("a.js", "const re = /[/]x/g;\nlet y = 1; // gone\n")
        self.assertIn("[/]x", out)
        self.assertNotIn("gone", out)

    def test_division_is_not_treated_as_regex(self) -> None:
        """`a / b / c` is arithmetic; misreading it would swallow real code."""
        out = self.assert_masked("a.js", "const q = a / b / c;\nconst z = 2; // gone\n")
        self.assertIn("a / b / c", out)
        self.assertIn("const z = 2;", out)
        self.assertNotIn("gone", out)

    def test_comment_inside_template_substitution_is_stripped(self) -> None:
        """Inside `${...}` the language is code again, so comments must go."""
        out = self.assert_masked("a.js", "const t = `v ${a /* gone */ + b} w`;\n")
        self.assertNotIn("gone", out)
        self.assertIn("` v ", out.replace("`v ", "` v "))

    def test_double_slash_inside_string_survives(self) -> None:
        """A URL in a string literal is not a comment."""
        out = self.assert_masked("a.ts", 'const u = "http://x/y";\n// gone\n')
        self.assertIn("http://x/y", out)
        self.assertNotIn("gone", out)

    def test_block_comment_marker_inside_string_survives(self) -> None:
        """`/*` in a string must not open a block comment."""
        out = self.assert_masked("a.c", 'char *s = "/* not */";\nint x = 1;\n')
        self.assertIn("/* not */", out)
        self.assertIn("int x = 1;", out)

    def test_escaped_quotes_preserve_comment_markers(self) -> None:
        """An escaped closing quote must keep the following text inside the string."""
        for quote in ('"', "'", "`"):
            with self.subTest(quote=quote):
                literal = f"{quote}escaped\\{quote} // keep{quote}"
                out = self.assert_masked("a.js", f"const s = {literal}; // gone\n")
                self.assertIn(literal, out)
                self.assertNotIn("gone", out)

    def test_rust_nested_block_comments(self) -> None:
        """Rust allows nesting, so the depth counter must be exercised."""
        out = self.assert_masked("a.rs", "let x = 1; /* a /* b */ c */\nlet y = 2;\n")
        for claim in ("a", "b", "c"):
            self.assertNotIn(claim, out.replace("let", ""))
        self.assertIn("let y = 2;", out)

    def test_rust_lifetime_does_not_open_a_string(self) -> None:
        """`'static` is a lifetime, so the comment after it must still go."""
        out = self.assert_masked("a.rs", "fn value() -> &'static str { // always safe\n")
        self.assertNotIn("always safe", out)
        self.assertIn("&'static str {", out)

    def test_rust_char_literals_still_hide_comment_markers(self) -> None:
        """`'/'` and `'\\''` are char literals; the text after them is code."""
        out = self.assert_masked("a.rs", "let a = '/'; let b = '\\''; // gone\n")
        self.assertIn("let a = '/'; let b = '\\'';", out)
        self.assertNotIn("gone", out)

    def test_template_substitution_tracks_nested_object_braces(self) -> None:
        """A `}` inside `${{...}}` must not close the interpolation."""
        out = self.assert_masked("a.js", "const value = `${{key: 1} /* hidden */}`;\n")
        self.assertNotIn("hidden", out)
        self.assertIn("{key: 1}", out)


class HashStripTest(PositionContractTest):
    """Shell-family `#` handling is position-sensitive."""

    def test_shell_parameter_expansion_survives(self) -> None:
        """`${#arr[@]}` is a length expansion, not a comment."""
        out = self.assert_masked("a.sh", "n=${#arr[@]}  # gone\n")
        self.assertIn("${#arr[@]}", out)
        self.assertNotIn("gone", out)

    def test_hash_inside_quotes_survives(self) -> None:
        """A quoted `#` is data."""
        out = self.assert_masked("a.sh", 's="a#b"  # gone\n')
        self.assertIn("a#b", out)
        self.assertNotIn("gone", out)

    def test_url_fragment_survives(self) -> None:
        """A `#` with no preceding whitespace does not open a comment."""
        out = self.assert_masked("a.sh", "url=http://x#frag\n# gone\n")
        self.assertIn("http://x#frag", out)
        self.assertNotIn("gone", out)

    def test_nix_files_are_stripped(self) -> None:
        """A Nix dotfiles repo's diffs are mostly .nix files."""
        out = self.assert_masked("a.nix", "{ x = 1; # gone\n}\n")
        self.assertNotIn("gone", out)
        self.assertIn("x = 1;", out)

    def test_nix_indented_string_preserves_hashes(self) -> None:
        """`#` inside `''...''` is data, including a quoted shell comment."""
        src = "let\n  script = ''\n    echo \"# keep\"\n  '';\n# remove\n"
        out = self.assert_masked("example.nix", src)
        self.assertIn('echo "# keep"', out)
        self.assertNotIn("remove", out)

    def test_nix_escaped_indent_delimiters_stay_inside_string(self) -> None:
        """`'''`, `''$`, and `''\\` do not close an indented string."""
        src = "''\n  echo '''\n  echo ''$\n  echo ''\\\n'';\n# gone\n"
        out = self.assert_masked("a.nix", src)
        self.assertIn("echo '''", out)
        self.assertNotIn("gone", out)

    def test_nix_nested_indented_string_in_interpolation(self) -> None:
        """`${ '' ... '' }` is a nested string; an unquoted `#` in it is data."""
        src = "''\n  ${\n    ''\n      echo # keep\n    ''\n  }\n'';\n# gone\n"
        out = self.assert_masked("a.nix", src)
        self.assertIn("echo # keep", out)
        self.assertNotIn("gone", out)

    def test_nix_interpolation_comments_are_stripped(self) -> None:
        """Inside `${...}` the language is Nix again, so `#` is a comment."""
        src = "''\n  ${foo # gone\n  }\n'';\n"
        out = self.assert_masked("a.nix", src)
        self.assertNotIn("gone", out)
        self.assertIn("${foo", out)

    def test_extensionless_known_stems_are_stripped(self) -> None:
        """A Justfile has comment syntax even with no suffix."""
        out = self.assert_masked("Justfile", "# gone\nbuild:\n    echo hi\n")
        self.assertNotIn("gone", out)
        self.assertIn("echo hi", out)

    def test_yaml_block_scalar_hash_is_data(self) -> None:
        """An indented `#` in a `|` or `>` block scalar is string content."""
        src = "pattern: |\n  # deny\nlist:\n  - >-\n    # keep\nother: 1 # gone\n"
        out = self.assert_masked("a.yaml", src)
        self.assertIn("# deny", out)
        self.assertIn("# keep", out)
        self.assertNotIn("gone", out)

    def test_yaml_block_scalar_quote_does_not_desync(self) -> None:
        """An unmatched quote inside a block scalar must not hide later comments."""
        out = self.assert_masked("a.yml", 'run: |\n  echo "hi\nx: 1 # gone\n')
        self.assertIn('echo "hi', out)
        self.assertNotIn("gone", out)


class SqlAndXmlStripTest(PositionContractTest):
    """The remaining supported families."""

    def test_sql_escaped_quote_does_not_desync(self) -> None:
        """`''` is an escaped quote, not an empty string ending the literal."""
        out = self.assert_masked("a.sql", "SELECT 'it''s -- fine';\n-- gone\n")
        self.assertIn("it''s -- fine", out)
        self.assertNotIn("gone", out)

    def test_sql_block_comment_is_stripped(self) -> None:
        """The /* */ state must blank its body and hand control back to code."""
        out = self.assert_masked("a.sql", "SELECT 1 /* gone */, 2;\nSELECT 3;\n")
        self.assertNotIn("gone", out)
        self.assertIn("SELECT 3;", out)
        self.assertIn(", 2;", out)

    def test_sql_block_comment_spanning_lines_reopens_code(self) -> None:
        """A multi-line block must not swallow the statement that follows it."""
        src = "SELECT 1;\n/* gone\n   also gone */\nSELECT 2;\n"
        out = self.assert_masked("a.sql", src)
        self.assertNotIn("gone", out)
        self.assertIn("SELECT 2;", out)

    def test_sql_block_marker_in_string_is_not_a_comment(self) -> None:
        """`/*` inside a literal is data; stripping it would delete real SQL."""
        out = self.assert_masked("a.sql", "SELECT '/* not */ x';\n-- gone\n")
        self.assertIn("/* not */ x", out)
        self.assertNotIn("gone", out)

    def test_xml_comment_is_stripped(self) -> None:
        """HTML/XML comments carry the same claims as code comments."""
        out = self.assert_masked("a.html", "<p>keep</p><!-- gone -->\n")
        self.assertIn("keep", out)
        self.assertNotIn("gone", out)

    def test_xml_comment_marker_in_attribute_is_not_a_comment(self) -> None:
        """`<!--` inside a quoted attribute is text, not a comment opener."""
        src = '<img alt="see <!-- this --> for details">\n<!-- gone -->\n'
        out = self.assert_masked("a.html", src)
        self.assertIn("see <!-- this --> for details", out)
        self.assertNotIn("gone", out)

    def test_xml_single_quoted_attribute_is_preserved(self) -> None:
        """Attribute quoting is either quote character, not just double."""
        out = self.assert_masked("a.svg", "<path d='<!-- keep -->'/><!-- gone -->\n")
        self.assertIn("<!-- keep -->", out)
        self.assertNotIn("gone", out)

    def test_xml_comment_after_a_tag_still_strips(self) -> None:
        """Leaving the tag state must re-arm comment detection."""
        out = self.assert_masked("a.xml", '<a href="x">y</a><!-- gone -->\n')
        self.assertIn('<a href="x">y</a>', out)
        self.assertNotIn("gone", out)


# (file name, source, text that must survive, text that must be removed).
# Each row pins one comment, docstring, or literal style of a major language.
STYLE_CASES: list[tuple[str, str, list[str], list[str]]] = [
    # Python: single-quoted and prefixed docstrings, implicit concatenation,
    # line continuations, and comments that are really directives.
    ("a.py", "def f():\n    'Single doc.'\n    return 1\n", ["return 1"], ["Single doc"]),
    ("a.py", 'R"""Raw doc."""\nx = 1\n', ["x = 1"], ["Raw doc"]),
    ("a.py", "def f():\n    '''Multi\n    line.'''\n", [], ["Multi", "line."]),
    ("a.py", "x = 1\n'alpha' 'beta'\n", ["x = 1"], ["alpha", "beta"]),
    ("a.py", "def f():\n    'cont\\\n    inued'\n", [], ["cont", "inued"]),
    (
        "a.py",
        "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# gone\nx = 1\n",
        ["#!/usr/bin/env python3", "coding: utf-8"],
        ["gone"],
    ),
    (
        "a.py",
        '# /// script\n# dependencies = ["rich"]\n# ///\n# gone\n',
        ['# dependencies = ["rich"]'],
        ["gone"],
    ),
    ("a.pyi", 'def f() -> int:\n    """Stub doc."""\n', [], ["Stub doc"]),
    # JavaScript and TypeScript.
    ("a.mjs", "export const x = 1; // gone\n", ["export const x = 1;"], ["gone"]),
    (
        "a.tsx",
        'const a = <a href="x">https://example.com/docs</a>; // gone\n',
        ["https://example.com/docs"],
        ["gone"],
    ),
    (
        "a.ts",
        '/// <reference types="node" />\n/** Doc. */\nexport const x = 1;\n',
        ['/// <reference types="node" />'],
        ["Doc."],
    ),
    ("a.js", "#!/usr/bin/env node\nconst x = 1; // gone\n", ["#!/usr/bin/env node"], ["gone"]),
    # JVM, Swift, Dart, and C# text blocks, raw strings, and nested comments.
    (
        "A.java",
        'String s = """\n  // keep\n  """; // gone\n/** Javadoc. */\n',
        ["// keep"],
        ["gone", "Javadoc"],
    ),
    ("a.kt", 'val p = """C:\\"""; // gone\n', ['"""C:\\"""'], ["gone"]),
    (
        "a.kt",
        "/* outer /* inner */ tail */ val y = 1\n/** KDoc. */\n",
        ["val y = 1"],
        ["outer", "inner", "tail", "KDoc"],
    ),
    ("a.scala", "val s = 'sym; // gone\nval c = '\"'; // gone2\n", ["'\"'"], ["gone"]),
    (
        "a.swift",
        'let s = #"a "quoted" // keep"#  // gone\n/* outer /* inner */ tail */ let y = 1\n',
        ['#"a "quoted" // keep"#', "let y = 1"],
        ["gone", "outer", "inner", "tail"],
    ),
    ("a.swift", 'let s = """\n  // keep\n  """\n/// Doc.\n', ["// keep"], ["Doc."]),
    (
        "a.dart",
        "var s = r'C:\\'; // gone\nvar t = '''\n// keep\n''';\n/// Doc.\n",
        ["r'C:\\'", "// keep"],
        ["gone", "Doc."],
    ),
    (
        "a.cs",
        ('var p = @"C:\\dir\\"; // gone\nvar q = @"say ""hi"" // keep";\n'
        "/// <summary>Doc.</summary>\n"),
        ['""hi"" // keep'],
        ["gone", "summary"],
    ),
    ("a.cs", 'var r = """\n  // keep "quoted"\n  """; // gone\n', ['// keep "quoted"'], ["gone"]),
    ("a.groovy", "def re = /a\\/\\/b/ // gone\n", ["/a\\/\\/b/"], ["gone"]),
    # C and C++: raw strings, digit separators, char literals.
    (
        "a.cpp",
        'auto s = R"(a "// keep" b)"; // gone\nint n = 1\'000\'000; // gone2\n',
        ['R"(a "// keep" b)"', "1'000'000;"],
        ["gone"],
    ),
    ("a.cpp", 'auto s = R"x(a )" // keep)x"; // gone\n', ["// keep"], ["gone"]),
    ("a.c", "char c = '\"'; /* gone */ char d = '/';\n", ["'\"'", "'/'"], ["gone"]),
    ("a.cu", "int x = 1; // gone\n", ["int x = 1;"], ["gone"]),
    # Go: raw strings and build directives.
    (
        "a.go",
        ("//go:build linux\n// +build linux\n\n// Package doc.\npackage a\n"
        "var s = `C:\\` // gone\n//go:embed x.txt\n"),
        ["//go:build linux", "// +build linux", "//go:embed x.txt", "`C:\\`"],
        ["Package doc", "gone"],
    ),
    # Rust: raw strings, doc attributes, doc comments, lifetimes.
    (
        "a.rs",
        ('let s = r#"a "// keep" b"#; // gone\n#[doc = "Attr doc."]\n'
        "fn f<'a>(x: &'a str) {} // gone2\n"),
        ['r#"a "// keep" b"#', "fn f<'a>(x: &'a str) {}"],
        ["gone", "Attr doc"],
    ),
    (
        "a.rs",
        '//! Crate doc.\n/// Item doc.\nfn g() { let s = "multi\n// keep\n"; }\n',
        ["// keep"],
        ["Crate doc", "Item doc"],
    ),
    # PHP: attributes, hash comments, heredocs, HTML outside the PHP tags.
    (
        "a.php",
        ("<?php\n#[Attr]\n$a = 1; # gone\n// gone2\n$s = <<<EOT\n  # keep\n  EOT;\n"
        "/** Doc. */\n?>\n<p>don't // keep2</p>\n"),
        ["#[Attr]", "# keep", "don't // keep2"],
        ["gone", "Doc."],
    ),
    # Stylesheets and JSON with comments.
    (
        "a.css",
        "a { background: url(http://x/y.png); } /* gone */\n",
        ["url(http://x/y.png)"],
        ["gone"],
    ),
    ("a.scss", "$u: url(http://x/y.png); // gone\n/* gone2 */\n", ["url(http://x/y.png)"], ["gone"]),
    (
        "tsconfig.json",
        '{\n  // gone\n  "a": "http://x" /* gone2 */\n}\n',
        ['"a": "http://x"'],
        ["gone"],
    ),
    # Shells.
    (
        "a.sh",
        "#!/bin/bash\ncat <<EOF\n# keep\nEOF\necho it\\'s # gone\ncat <<-'X'\n\t# keep2\n\tX\n",
        ["#!/bin/bash", "# keep", "# keep2", "it\\'s"],
        ["gone"],
    ),
    ("a.sh", "x=$((1<<2)) # gone\n", ["x=$((1<<2))"], ["gone"]),
    ("a.bash", "a=1;# gone\n", ["a=1;"], ["gone"]),
    (".zshrc", "alias x='y' # gone\n", ["alias x='y'"], ["gone"]),
    (
        "a.ps1",
        ("#Requires -Version 7\n<#\n.SYNOPSIS\nHelp doc.\n#>\n$s = 'it''s # keep' # gone\n"
        '$h = @"\n# keep2\n"@\n'),
        ["#Requires -Version 7", "'it''s # keep'", "# keep2"],
        ["Help doc", "gone"],
    ),
    # Ruby and Perl: block docs, heredocs, regex and quote-like literals.
    (
        "a.rb",
        ("# frozen_string_literal: true\n=begin\nBlock doc.\n=end\nx = /a#b/ # gone\n"
        "s = <<~SQL\n  # keep\nSQL\nc = ?#\n__END__\n# data\n"),
        ["frozen_string_literal: true", "/a#b/", "# keep", "?#", "# data"],
        ["Block doc", "gone"],
    ),
    ("Gemfile", "gem 'rails' # gone\n", ["gem 'rails'"], ["gone"]),
    (
        "a.pl",
        "my $n = $#a; # gone\n=pod\n\nPOD doc.\n\n=cut\nmy @s = qw(a # keep);\n$x =~ s#a#b#;\n",
        ["$#a;", "qw(a # keep)", "s#a#b#"],
        ["gone", "POD doc"],
    ),
    # Lua, Haskell, OCaml, F#, Erlang, Elixir, Julia, R, Clojure, Lisp, Zig, Solidity.
    (
        "a.lua",
        ("local s = [[ -- keep ]] -- gone\n--[==[ block\ngone2 ]==] local y = 1\n"
        "---@param x number\n"),
        ["[[ -- keep ]]", "local y = 1"],
        ["gone", "block", "@param"],
    ),
    (
        "a.hs",
        ("{-# LANGUAGE GADTs #-}\nx = a --> b -- gone\n{- outer {- inner -} tail -}\n"
        "f' = 'a' -- gone2\n-- | Haddock.\n"),
        ["{-# LANGUAGE GADTs #-}", "a --> b", "f' = 'a'"],
        ["gone", "outer", "inner", "tail", "Haddock"],
    ),
    (
        "a.ml",
        ("let f = ( * ) (* outer (* inner *) tail *)\nlet c = '\"' (* gone *)\n"
        "type 'a t = 'a list\n"),
        ["( * )", "'\"'", "type 'a t = 'a list"],
        ["outer", "inner", "tail", "gone"],
    ),
    (
        "a.fs",
        '/// Doc.\nlet s = @"C:\\" // gone\nlet t = """// keep"""\n',
        ['"""// keep"""'],
        ["Doc.", "gone"],
    ),
    ("a.erl", 'X = $%, % gone\nS = "% keep".\n', ["$%", '"% keep"'], ["gone"]),
    (
        "a.ex",
        ('defmodule A do\n  @moduledoc """\n  Module doc.\n  """\n  @doc "Fun doc."\n'
        "  def f, do: ?# # gone\n  def g, do: ~r/#keep/\nend\n"),
        ["?#", "~r/#keep/"],
        ["Module doc", "Fun doc", "gone"],
    ),
    (
        "a.jl",
        ('"""\n    f(x)\n\nJulia doc.\n"""\nfunction f(x) x\' end # gone\n'
        '#= outer\n#= inner =# tail =#\ns = "keep # this"\n'),
        ["x'", '"keep # this"'],
        ["Julia doc", "gone", "outer", "inner", "tail"],
    ),
    (
        "a.r",
        "#' Roxygen doc.\nf <- function(x) x # gone\ns <- r\"(a # keep)\"\n",
        ['r"(a # keep)"'],
        ["Roxygen", "gone"],
    ),
    (
        "a.clj",
        '(defn f\n  "Fn doc."\n  [x] x) ; gone\n(def c \\;) ; gone2\n(def s "keep ; this")\n',
        ["\\;", '"keep ; this"'],
        ["Fn doc", "gone"],
    ),
    ("a.el", '(defun f (x)\n  "Fn doc."\n  x) ; gone\n', ["x)"], ["Fn doc", "gone"]),
    (
        "a.zig",
        "const s =\n    \\\\ http://x // keep\n; // gone\n/// Doc.\n",
        ["http://x // keep"],
        ["gone", "Doc."],
    ),
    ("a.sol", "/// @notice Doc.\nuint x = 1; // gone\n", ["uint x = 1;"], ["Doc.", "gone"]),
    # SQL: dollar quotes, quoted identifiers, E-strings, nested comments.
    (
        "a.sql",
        ("CREATE FUNCTION f() RETURNS int AS $$ SELECT '-- keep' -- gone0\n$$ LANGUAGE sql; -- gone\n"
        'SELECT "a--b" FROM t; /* outer /* inner */ tail */\n'
        "SELECT E'it\\'s -- keep2';\n"),
        ["SELECT '-- keep'", '"a--b"', "E'it\\'s -- keep2'"],
        ["gone", "outer", "inner", "tail"],
    ),
    # Config formats.
    ("a.yaml", "msg: don't # gone\nq: 'a # keep'\n", ["don't", "'a # keep'"], ["gone"]),
    ("a.toml", "a = 1# gone\ns = '''\n# keep\n'''\n", ["# keep"], ["gone"]),
    ("setup.cfg", "[x]\n; gone\n# gone2\nvalue = a # keep\n", ["a # keep"], ["gone"]),
    ("a.properties", "! gone\n# gone2\nkey = a # keep\n", ["a # keep"], ["gone"]),
    (
        "Dockerfile",
        "# syntax=docker/dockerfile:1\n# gone\nENV A=b # keep\nRUN <<EOF\n# keep2\nEOF\n",
        ["# syntax=docker/dockerfile:1", "b # keep", "# keep2"],
        ["gone"],
    ),
    (".gitignore", "# gone\nfoo #keep\n", ["foo #keep"], ["gone"]),
    (
        "Makefile",
        'all:\n\techo "a # keep" # gone\nX = 1 \\# keep2\n',
        ['"a # keep"', "\\# keep2"],
        ["gone"],
    ),
    (
        "justfile",
        "# gone\nbuild:\n    #!/usr/bin/env bash\n    echo hi # gone2\n",
        ["#!/usr/bin/env bash", "echo hi"],
        ["gone"],
    ),
    (
        "requirements-dev.txt",
        "requests==2.0 # gone\npkg @ https://x/y#egg=z\n",
        ["#egg=z"],
        ["gone"],
    ),
    (
        "CMakeLists.txt",
        '#[[ block\ngone ]]\nset(X "a # keep") # gone2\n',
        ['"a # keep"'],
        ["block", "gone"],
    ),
    (
        "a.tf",
        '# gone\n// gone2\n/* gone3 */\nx = "${var.a} # keep"\ny = <<-EOT\n  # keep2\n  EOT\n',
        ["# keep", "# keep2"],
        ["gone"],
    ),
    ("a.nix", "{ x = 1; /* gone */ y = a // b; }\n", ["a // b"], ["gone"]),
    (
        "a.graphql",
        ('"""\nType doc.\n"""\ntype A {\n  "Field doc."\n'
        '  f(arg: String = "keep"): Int # gone\n}\n'),
        ['"keep"'],
        ["Type doc", "Field doc", "gone"],
    ),
    # Markup with embedded code.
    (
        "a.html",
        ('<script>\nconst s = "<!-- keep -->"; // gone\n</script>\n'
        "<style>a { color: red; } /* gone2 */</style>\n<![CDATA[ <!-- keep2 --> ]]>\n"
        "<!-- gone3 -->\n"),
        ['"<!-- keep -->"', "<!-- keep2 -->"],
        ["gone"],
    ),
    (
        "a.vue",
        ('<template><p>x</p><!-- gone --></template>\n<script lang="ts">\n'
        "const x: number = 1; // gone2\n</script>\n"
        '<style lang="scss">\n$c: red; // gone3\n</style>\n'),
        ["const x: number = 1;", "$c: red;"],
        ["gone"],
    ),
    ("a.html", '<script type="text/template"><p>// keep</p></script>\n', ["// keep"], []),
    # Interpolation that nests quotes, found in real code.
    (
        "a.sh",
        'tag="$(curl "${u}" | grep \'"tag_name":\' | sed \'s/.*"([^"]+)".*/\\1/\')"\n# gone\n',
        ['grep \'"tag_name":\''],
        ["gone"],
    ),
    (
        "a.rb",
        'x << "#{items.map do |n|\n  "  - `#{n}` failed (#{s})."\nend.join}"\n# gone\n',
        ["failed (#{s})."],
        ["gone"],
    ),
    ("a.rb", "R = /\\A\n  (?:#{HEX}) | # gone\n  x/x\n", ["(?:#{HEX}) |"], []),
    ("a.rb", "R = /\n  #{A}\n/x\n", ["#{A}"], []),
    ("a.rb", "c = '\\1'\n/(#{f})(.*)/m\n", ["/(#{f})(.*)/m"], []),
    ("a.kt", 'val s = "${m["k"]} // keep" // gone\n', ['"${m["k"]} // keep"'], ["gone"]),
    ("a.swift", 'let s = "\\(f("a")) // keep" // gone\n', ['"\\(f("a")) // keep"'], ["gone"]),
    ("a.json5", "{ $schema: 'https://x/y.json', // gone\n}\n", ["'https://x/y.json'"], ["gone"]),
    (
        "CMakeLists.txt",
        'set(F -isysroot \\"${ROOT}\\")\n# gone\n',
        ['\\"${ROOT}\\"'],
        ["gone"],
    ),
    ("Makefile", "all:\n\t@# gone\n\t@echo hi\n", ["@echo hi"], ["gone"]),
]


class LanguageStyleTest(PositionContractTest):
    """Every listed language keeps its literals and loses its comments and docs."""

    def test_styles(self) -> None:
        """Each row must strip as a space mask with the expected text in and out."""
        for name, source, keep, drop in STYLE_CASES:
            with self.subTest(name=name, source=source[:40]):
                out = self.assert_masked(name, source)
                for text in keep:
                    self.assertIn(text, out)
                for text in drop:
                    self.assertNotIn(text, out)


class DispatchTest(unittest.TestCase):
    """Unsupported input must degrade loudly, never silently."""

    def test_unknown_language_is_flagged(self) -> None:
        """An unstripped file must say so in its manifest action."""
        _, action = strip_context.strip_source("a.weird", "# whatever\n")
        self.assertEqual(action, "copied-verbatim (unknown language)")

    def test_unparseable_python_is_flagged(self) -> None:
        """A tokenize failure degrades rather than raising."""
        _, action = strip_context.strip_source("a.py", "def (:\n")
        self.assertTrue(action.startswith("copied-verbatim"), action)

    def test_validation_rejects_a_stripper_that_deletes_code(self) -> None:
        """The mask check is the safety net for every stripper bug."""
        reason = strip_context.validate_strip("a.js", "const x = 1;\n", "const x\n")
        self.assertIsNotNone(reason)

    def test_validation_accepts_a_faithful_mask(self) -> None:
        """A correct strip must not be rejected."""
        self.assertIsNone(
            strip_context.validate_strip(
                "a.js", "let x = 1; // c\n", "let x = 1;     \n"
            )
        )


class DiffOutputTest(unittest.TestCase):
    """The stripped diff is the artifact the blind reviewer consumes."""

    def test_file_without_trailing_newline_yields_applicable_patch(self) -> None:
        """A missing final newline must not glue lines or file headers together."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def run(*a: str) -> None:
                """Run a git command in the fixture repo."""
                subprocess.run(
                    ["git", "-C", str(repo), *a], check=True, capture_output=True
                )

            run("init", "-q", "-b", "main")
            run("config", "user.email", "t@example.com")
            run("config", "user.name", "t")
            (repo / "one.py").write_text("a = 1\nb = 2")  # no trailing newline
            (repo / "two.py").write_text("c = 3\n")
            run("add", "-A")
            run("commit", "-qm", "base")
            base = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repo / "one.py").write_text("a = 9\nb = 3")
            (repo / "two.py").write_text("c = 4\n")
            out = repo / "_out"
            rc = strip_context.main(
                ["diff", "--repo", str(repo), "--base", base, "--out", str(out)]
            )
            self.assertEqual(rc, 0)
            patch = (out / "stripped.diff").read_text()
            self.assertNotIn("b = 2+a = 9", patch)
            for line in patch.splitlines():
                self.assertFalse(
                    line.startswith("-") and "+" in line[1:] and "---" not in line,
                    f"glued diff line: {line!r}",
                )
            # --numstat parses the patch without consulting the worktree,
            # which the stripped text deliberately no longer matches.
            check = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "apply",
                    "--numstat",
                    str(out / "stripped.diff"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_untracked_file_is_included(self) -> None:
        """A newly added file is part of the change under review."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def run(*a: str) -> None:
                """Run a git command in the fixture repo."""
                subprocess.run(
                    ["git", "-C", str(repo), *a], check=True, capture_output=True
                )

            run("init", "-q", "-b", "main")
            run("config", "user.email", "t@example.com")
            run("config", "user.name", "t")
            (repo / "one.py").write_text("a = 1\n")
            run("add", "-A")
            run("commit", "-qm", "base")
            base = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repo / "one.py").write_text("a = 2\n")
            (repo / "new.py").write_text('"""Doc."""\nb = 3\n')
            out = repo / "_out"
            strip_context.main(
                ["diff", "--repo", str(repo), "--base", base, "--out", str(out)]
            )
            import json

            manifest = json.loads((out / "manifest.json").read_text())
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertIn("new.py", paths)
            self.assertNotIn("Doc.", (out / "head" / "new.py").read_text())

    def test_failure_on_either_side_survives_in_the_manifest(self) -> None:
        """A base that failed to strip must not be relabelled by a clean head."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for args in (
                ("init", "-q", "-b", "main"),
                ("config", "user.email", "t@example.com"),
                ("config", "user.name", "t"),
            ):
                subprocess.run(["git", "-C", str(repo), *args], check=True)
            (repo / "a.py").write_text("def (:\nx = 1\n")  # base cannot be parsed
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
            (repo / "a.py").write_text("x = 2\n")
            out = repo / "_out"
            strip_context.main(["diff", "--repo", str(repo), "--out", str(out)])
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertTrue(manifest["files"][0]["action"].startswith("copied-verbatim"))



class MechanicalModeTest(unittest.TestCase):
    """Mechanical units carry changed code lines and nothing else."""

    def run_mechanical(self, base_files: dict[str, str], head_files: dict[str, str]) -> Path:
        """Commit ``base_files``, write ``head_files``, and run mechanical mode.

        Args:
            base_files: Committed file contents by relative path.
            head_files: Worktree file contents by relative path.

        Returns:
            The output directory.
        """
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", tmp], check=False))
        repo = Path(tmp) / "repo"
        repo.mkdir()

        def run(*a: str) -> None:
            """Run a git command in the fixture repo."""
            subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)

        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        for rel, text in base_files.items():
            (repo / rel).write_text(text)
        run("add", "-A")
        run("commit", "-qm", "base")
        for rel, text in head_files.items():
            (repo / rel).write_text(text)
        out = Path(tmp) / "out"
        rc = strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
        self.assertEqual(rc, 0)
        return out

    def test_only_changed_code_lines_reach_the_unit(self) -> None:
        """Comment, docstring, TODO, and whitespace edits vanish; code edits stay."""
        out = self.run_mechanical(
            {"secret_auth.py": '"""Old doc."""\nimport os\n\n\ndef f(a, b):\n    return a+b\n'},
            {
                "secret_auth.py": '"""New doc."""\nimport os\n# TODO later\n\n'
                "def f(a, b):\n    return a - b  # safe\n"
            },
        )
        unit = (out / "units" / "f01.py.diff").read_text()
        self.assertEqual(unit, "file f01.py\n-6|    return a+b\n+6|    return a - b\n")
        self.assertNotIn("secret_auth", "".join(p.read_text() for p in (out / "units").iterdir()))

    def test_added_docstring_writes_no_unit(self) -> None:
        """A new docstring, single or multi-line, is documentation, not code."""
        out = self.run_mechanical(
            {"a.py": "def f():\n    return 1\n"},
            {"a.py": "def f():\n    '''One.\n\n    Two.\n    '''\n    return 1\n"},
        )
        self.assertEqual(list((out / "units").iterdir()), [])

    def test_noise_only_change_writes_no_unit(self) -> None:
        """A change that touches only comments and spacing has nothing to review."""
        out = self.run_mechanical(
            {"a.js": "let x = 1; // one\n"}, {"a.js": "let  x = 1;   // uno\n"}
        )
        self.assertEqual(list((out / "units").iterdir()), [])
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["files"][0]["action"], "no-code-change")

    def test_python_reindent_is_a_code_change(self) -> None:
        """Leading whitespace is syntax in Python, so a re-indent must surface."""
        out = self.run_mechanical(
            {"a.py": "if x:\n    y()\n    z()\n"}, {"a.py": "if x:\n    y()\nz()\n"}
        )
        self.assertIn("+3|z()", (out / "units" / "f01.py.diff").read_text())

    def test_symlink_is_read_as_its_target_path(self) -> None:
        """A changed symlink must not leak the content of the file it points at."""
        outside = Path(tempfile.mkdtemp()) / "secret.py"
        outside.write_text("TOKEN = 'leaked'\n")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(outside.parent)], check=False))
        out = self.run_mechanical({"a.py": "x = 1\n"}, {})
        repo = Path(json.loads((out / "manifest.json").read_text())["repo"])
        (repo / "link.py").symlink_to(outside)
        strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
        units = "".join(p.read_text() for p in (out / "units").iterdir())
        self.assertNotIn("leaked", units)

    def test_symlinked_parent_dir_is_not_followed(self) -> None:
        """Replacing a tracked dir with a symlink must not read outside the repo."""
        outside = Path(tempfile.mkdtemp())
        (outside / "k.py").write_text("TOKEN = 'leaked'\n")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(outside)], check=False))
        out = self.run_mechanical({"a.py": "x = 1\n"}, {})
        repo = Path(json.loads((out / "manifest.json").read_text())["repo"])
        (repo / "d").mkdir()
        (repo / "d" / "k.py").write_text("y = 1\n")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "dir"], check=True)
        subprocess.run(["rm", "-rf", str(repo / "d")], check=True)
        (repo / "d").symlink_to(outside)
        strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
        units = "".join(p.read_text() for p in (out / "units").iterdir())
        self.assertNotIn("leaked", units)
        self.assertIn("-1|y = 1", units)

    def test_whitespace_between_tokens_is_a_code_change(self) -> None:
        """A new space can split one shell argument into two."""
        out = self.run_mechanical(
            {"a.sh": "rm -rf /tmp/build\n"}, {"a.sh": "rm  -rf / tmp/build\n"}
        )
        self.assertIn("+1|rm  -rf / tmp/build", (out / "units" / "f01.sh.diff").read_text())

    def test_whitespace_run_length_is_not_a_change(self) -> None:
        """Collapsing a run of spaces is formatting, not code."""
        out = self.run_mechanical({"a.sh": "rm -rf /tmp\n"}, {"a.sh": "rm   -rf  /tmp  \n"})
        self.assertEqual(list((out / "units").iterdir()), [])

    def test_makefile_tab_to_spaces_is_a_code_change(self) -> None:
        """A recipe line must start with a tab, so retabbing breaks make."""
        out = self.run_mechanical(
            {"Makefile": "all:\n\techo hi\n"}, {"Makefile": "all:\n    echo hi\n"}
        )
        self.assertIn("+2|    echo hi", (out / "units" / "f01-Makefile.diff").read_text())

    def test_non_ascii_file_name_is_reviewed(self) -> None:
        """Git quotes such names unless -z is used; the change must not vanish."""
        out = self.run_mechanical({"caf\u00e9.py": "x = 1\n"}, {"caf\u00e9.py": "x = 2\n"})
        self.assertIn("+1|x = 2", (out / "units" / "f01.py.diff").read_text())

    def test_submodule_bump_does_not_crash(self) -> None:
        """A submodule path is a directory, not a file to read."""
        out = self.run_mechanical({"a.py": "x = 1\n"}, {})
        repo = Path(json.loads((out / "manifest.json").read_text())["repo"])
        sub = repo / "sub"
        sub.mkdir()
        # CI has no global git identity, so the inner repo needs its own.
        ident = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
        for args in (("init", "-q"), (*ident, "commit", "-q", "--allow-empty", "-m", "s1")):
            subprocess.run(["git", "-C", str(sub), *args], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "add", "sub"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "sub"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(sub), *ident, "commit", "-q", "--allow-empty", "-m", "s2"],
            check=True,
            capture_output=True,
        )
        rc = strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
        self.assertEqual(rc, 0)

    def test_unknown_language_is_omitted_not_copied(self) -> None:
        """A file whose comments cannot be removed must not reach a reviewer."""
        out = self.run_mechanical({"a.vb": "x = 1\n"}, {"a.vb": "x = 2 ' why\n"})
        self.assertEqual(list((out / "units").iterdir()), [])
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertTrue(manifest["files"][0]["action"].startswith("omitted"))

    def test_rerun_removes_stale_units_and_results(self) -> None:
        """A rerun after the change is reverted must leave nothing to review."""
        out = self.run_mechanical({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
        (out / "results").mkdir()
        (out / "results" / "f01.py.json").write_text("{}")
        repo = Path(json.loads((out / "manifest.json").read_text())["repo"])
        (repo / "a.py").write_text("x = 1\n")
        strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
        self.assertEqual(list((out / "units").iterdir()), [])
        self.assertFalse((out / "results").exists())

    def test_unchanged_rename_has_no_code_change(self) -> None:
        """A renamed file is compared with its original path, not as all-new."""
        out = self.run_mechanical({"before.py": "x = 1\ny = 2\n"}, {})
        repo = Path(json.loads((out / "manifest.json").read_text())["repo"])
        subprocess.run(["git", "-C", str(repo), "mv", "before.py", "after.py"], check=True)
        strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
        self.assertEqual(list((out / "units").iterdir()), [])
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(
            manifest["files"],
            [{"path": "after.py", "base_path": "before.py", "action": "no-code-change"}],
        )


def load_mechanical_review() -> ModuleType:
    """Load the fan-out script as a module despite its non-importable filename.

    Returns:
        The imported module.
    """
    loader = SourceFileLoader("mechanical_review", str(SCRIPT.with_name("mechanical_review.py")))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class MechanicalReviewArgvTest(unittest.TestCase):
    """The reviewer process must start with no tools and no customizations."""

    def test_reply_without_structured_output_is_a_failure(self) -> None:
        """A reply with no findings field must not read as a clean file."""
        module = load_mechanical_review()
        out = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(out)], check=False))
        for sub in ("units", "payloads", "results"):
            (out / sub).mkdir()
        unit = out / "units" / "f01.py.diff"
        unit.write_text("file f01.py\n+1|x = 1\n")
        fake = [sys.executable, "-c", "print('{\"is_error\": false}')"]
        result = module.review_unit(unit, out, fake, "no-such-repo-name")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no structured_output")

    def test_isolation_flags(self) -> None:
        """Dropping any of these flags lets non-diff text reach the model."""
        module = load_mechanical_review()
        argv = module.reviewer_argv("sonnet", "high")
        for flag in ("--safe-mode", "--strict-mcp-config", "--disable-slash-commands"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
        self.assertEqual(argv[argv.index("--system-prompt") + 1], module.BRIEF)


if __name__ == "__main__":
    unittest.main()
