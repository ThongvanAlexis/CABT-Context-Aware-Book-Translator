"""Tests for XHTML tokenizer: tokenize, detokenize, validate, and CLI."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Tokenize tests
# ---------------------------------------------------------------------------

class TestTokenize:
    """Tests for tokenize() function."""

    def test_simple_em_tag(self):
        """Simple <em> tag produces <em:1> token with registry."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize("<em>text</em>")
        assert "<em:1>" in text
        assert "</em:1>" in text
        assert "text" in text
        assert "em:1" in registry
        assert "/em:1" in registry

    def test_strong_tag(self):
        """<strong> tag produces <strong:N> token."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize("<strong>bold</strong>")
        assert "<strong:1>" in text
        assert "</strong:1>" in text
        assert "bold" in text

    def test_class_based_span(self):
        """<span class="system"> produces <span.system:N> token."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize('<span class="system">msg</span>')
        assert "<span.system:1>" in text
        assert "</span.system:1>" in text
        assert "msg" in text

    def test_self_closing_br(self):
        """<br/> produces <br:N/> self-closing token."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize("line1<br/>line2")
        assert "<br:1/>" in text
        assert "br:1" in registry

    def test_self_closing_img(self):
        """<img> tag preserves all attributes in registry."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize('<img src="x.png" alt="pic"/>')
        assert "<img:1/>" in text
        # Registry should store the full original tag
        assert 'src="x.png"' in registry["img:1"]

    def test_nested_tags(self):
        """Nested tags get unique numbered tokens."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize("<em><strong>text</strong></em>")
        # Both em and strong should have tokens
        assert "<em:" in text
        assert "<strong:" in text
        # Numbers should be unique
        keys = [k for k in registry.keys() if not k.startswith("/")]
        assert len(keys) == 2

    def test_multiple_same_type_tags(self):
        """Two <em> tags get distinct numbers."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize("<em>first</em> and <em>second</em>")
        em_keys = [k for k in registry.keys() if k.startswith("em:") and not k.startswith("/")]
        assert len(em_keys) == 2
        # They should have different numbers
        assert em_keys[0] != em_keys[1]

    def test_attributes_preserved(self):
        """Attributes stored verbatim in registry."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize('<div class="stat-box" id="s1">content</div>')
        div_keys = [k for k in registry.keys() if k.startswith("div")]
        assert len(div_keys) >= 1
        # The original tag should contain the attributes
        div_key = div_keys[0]
        assert 'class="stat-box"' in registry[div_key]
        assert 'id="s1"' in registry[div_key]

    def test_plain_text_passthrough(self):
        """Plain text with no tags returns unchanged with empty registry."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize("Just plain text here.")
        assert text == "Just plain text here."
        assert len(registry) == 0

    def test_body_extraction(self):
        """Full XHTML document: only body inner content is tokenized."""
        from xhtml_tokenizer import tokenize
        xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title></head>
<body><p>Hello <em>world</em></p></body>
</html>"""
        text, registry = tokenize(xhtml)
        # Body inner content should be tokenized
        assert "<em:" in text or "<p:" in text
        # The <html>, <head> tags should NOT appear as tokens
        assert "<html:" not in text
        assert "<head:" not in text

    def test_full_xhtml_round_trip_preserves_wrapper(self):
        """Full XHTML document round-trip preserves html/head/body wrapper."""
        from xhtml_tokenizer import tokenize, detokenize
        xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Test</title>
<link rel="stylesheet" type="text/css" href="../stylesheet.css"/>
</head>
<body><p>Hello <em>world</em></p></body>
</html>"""
        text, registry = tokenize(xhtml)
        # Wrapper should be stored in registry
        assert "__xhtml_prefix__" in registry
        assert "__xhtml_suffix__" in registry
        assert "stylesheet.css" in registry["__xhtml_prefix__"]
        # Round-trip should restore the full document
        restored = detokenize(text, registry)
        assert restored == xhtml

    def test_namespace_attributes_preserved(self):
        """Tags with xmlns attributes are stored correctly in registry."""
        from xhtml_tokenizer import tokenize
        text, registry = tokenize('<div xmlns="http://www.w3.org/1999/xhtml">content</div>')
        div_keys = [k for k in registry.keys() if k.startswith("div")]
        assert len(div_keys) >= 1


# ---------------------------------------------------------------------------
# Detokenize tests
# ---------------------------------------------------------------------------

class TestDetokenize:
    """Tests for detokenize() function."""

    def test_round_trip_simple(self):
        """Tokenize then detokenize produces original."""
        from xhtml_tokenizer import tokenize, detokenize
        original = "<em>text</em>"
        text, registry = tokenize(original)
        restored = detokenize(text, registry)
        assert restored == original

    def test_round_trip_nested(self):
        """Round-trip with nested tags."""
        from xhtml_tokenizer import tokenize, detokenize
        original = "<em><strong>text</strong></em>"
        text, registry = tokenize(original)
        restored = detokenize(text, registry)
        assert restored == original

    def test_round_trip_self_closing(self):
        """Round-trip with self-closing tags."""
        from xhtml_tokenizer import tokenize, detokenize
        original = "line1<br/>line2"
        text, registry = tokenize(original)
        restored = detokenize(text, registry)
        assert restored == original

    def test_round_trip_with_attributes(self):
        """Round-trip preserves all attributes."""
        from xhtml_tokenizer import tokenize, detokenize
        original = '<span class="notification">Level Up!</span>'
        text, registry = tokenize(original)
        restored = detokenize(text, registry)
        assert restored == original

    def test_round_trip_complex(self):
        """Round-trip with mixed tag types."""
        from xhtml_tokenizer import tokenize, detokenize
        original = '<p>Hello <em>world</em> and <strong>bold <br/>text</strong></p>'
        text, registry = tokenize(original)
        restored = detokenize(text, registry)
        assert restored == original

    def test_unrecognized_tokens_left_as_is(self):
        """Tokens not in registry are left unchanged."""
        from xhtml_tokenizer import detokenize
        text = "Hello <foo:99> world"
        registry = {}
        result = detokenize(text, registry)
        assert "<foo:99>" in result

    def test_round_trip_multiple_same_type(self):
        """Round-trip with multiple same-type tags."""
        from xhtml_tokenizer import tokenize, detokenize
        original = "<em>first</em> and <em>second</em>"
        text, registry = tokenize(original)
        restored = detokenize(text, registry)
        assert restored == original


# ---------------------------------------------------------------------------
# Validate tests
# ---------------------------------------------------------------------------

class TestValidateTokens:
    """Tests for validate_tokens() function."""

    def test_valid_same_tokens(self):
        """Same tokens in both texts -> valid."""
        from xhtml_tokenizer import validate_tokens
        original = "<em:1>text</em:1>"
        translated = "<em:1>texte</em:1>"
        result = validate_tokens(original, translated)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_missing_token(self):
        """Missing token in translated text -> error."""
        from xhtml_tokenizer import validate_tokens
        original = "<em:1>text</em:1>"
        translated = "texte"
        result = validate_tokens(original, translated)
        assert result["valid"] is False
        assert any("Missing" in e or "missing" in e.lower() for e in result["errors"])

    def test_extra_token(self):
        """Extra token in translated text -> error."""
        from xhtml_tokenizer import validate_tokens
        original = "<em:1>text</em:1>"
        translated = "<em:1>texte</em:1> <foo:99>"
        result = validate_tokens(original, translated)
        assert result["valid"] is False
        assert any("Extra" in e or "extra" in e.lower() for e in result["errors"])

    def test_unclosed_token(self):
        """Opening token without matching close -> error."""
        from xhtml_tokenizer import validate_tokens
        original = "<em:1>text</em:1>"
        translated = "<em:1>texte"
        result = validate_tokens(original, translated)
        assert result["valid"] is False
        assert any("Unclosed" in e or "unclosed" in e.lower() or "Missing" in e or "missing" in e.lower() for e in result["errors"])

    def test_valid_different_order(self):
        """Same tokens in different order -> valid (LLM may reorder)."""
        from xhtml_tokenizer import validate_tokens
        original = "<em:1>hello</em:1> <strong:2>world</strong:2>"
        translated = "<strong:2>monde</strong:2> <em:1>bonjour</em:1>"
        result = validate_tokens(original, translated)
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLI:
    """Tests for CLI subcommands."""

    @pytest.fixture
    def script_path(self):
        return str(Path(__file__).parent.parent / "cabt-cc" / "scripts" / "xhtml_tokenizer.py")

    def test_tokenize_cli(self, tmp_path, script_path):
        """CLI tokenize reads XHTML, writes tokenized text and registry."""
        input_file = tmp_path / "input.xhtml"
        input_file.write_text("<p>Hello <em>world</em></p>", encoding="utf-8")
        output_file = tmp_path / "output.txt"
        registry_file = tmp_path / "registry.json"

        result = subprocess.run(
            [sys.executable, script_path, "tokenize",
             "--input", str(input_file),
             "--output", str(output_file),
             "--registry", str(registry_file)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert output_file.exists()
        assert registry_file.exists()

        tokenized = output_file.read_text(encoding="utf-8")
        assert "<p:1>" in tokenized or "<em:" in tokenized  # XML-style tokens present

        registry = json.loads(registry_file.read_text(encoding="utf-8"))
        assert len(registry) > 0

    def test_detokenize_cli(self, tmp_path, script_path):
        """CLI detokenize restores XHTML from tokenized text + registry."""
        # First tokenize
        input_file = tmp_path / "input.xhtml"
        original = "<p>Hello <em>world</em></p>"
        input_file.write_text(original, encoding="utf-8")
        tokenized_file = tmp_path / "tokenized.txt"
        registry_file = tmp_path / "registry.json"

        subprocess.run(
            [sys.executable, script_path, "tokenize",
             "--input", str(input_file),
             "--output", str(tokenized_file),
             "--registry", str(registry_file)],
            capture_output=True, text=True
        )

        # Then detokenize
        restored_file = tmp_path / "restored.xhtml"
        result = subprocess.run(
            [sys.executable, script_path, "detokenize",
             "--input", str(tokenized_file),
             "--registry", str(registry_file),
             "--output", str(restored_file)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        restored = restored_file.read_text(encoding="utf-8")
        assert restored == original

    def test_validate_cli(self, tmp_path, script_path):
        """CLI validate compares token sets and outputs JSON."""
        original_file = tmp_path / "original.txt"
        translated_file = tmp_path / "translated.txt"
        original_file.write_text("<em:1>hello</em:1>", encoding="utf-8")
        translated_file.write_text("<em:1>bonjour</em:1>", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, script_path, "validate",
             "--original", str(original_file),
             "--translated", str(translated_file)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["valid"] is True

    def test_cli_missing_input(self, tmp_path, script_path):
        """Missing input file -> stderr error and exit code 1."""
        result = subprocess.run(
            [sys.executable, script_path, "tokenize",
             "--input", str(tmp_path / "nonexistent.xhtml"),
             "--output", str(tmp_path / "out.txt"),
             "--registry", str(tmp_path / "reg.json")],
            capture_output=True, text=True
        )
        assert result.returncode == 1
        assert result.stderr.strip() != ""
