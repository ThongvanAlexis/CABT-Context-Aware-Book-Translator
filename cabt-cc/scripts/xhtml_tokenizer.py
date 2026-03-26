"""
XHTML tokenizer for CABT translation pipeline.

Replaces XHTML tags with semantic XML-style tokens before sending chapter
text to translation agents, and restores the original tags after translation.
Includes token validation to detect corruption.

Token format:
    Opening:      <tag_name:N>
    Closing:      </tag_name:N>
    Self-closing: <tag_name:N/>

Where tag_name is the lowercased element name, optionally suffixed with
.classname if a class attribute is present. N is a unique counter.

Why XML-style tokens: LLMs are trained on massive amounts of HTML/XML and
learn that tags are structural markup, not content to translate or modify.
This is deeply embedded in model weights -- an LLM won't translate <em:1>
the way it might mangle arbitrary Unicode delimiters like guillemets (« »),
which are actual quotation marks in French, Russian, and other languages.

Usage as module:
    from xhtml_tokenizer import tokenize, detokenize, validate_tokens

Usage as CLI:
    python xhtml_tokenizer.py tokenize --input file.xhtml --output file.tokenized --registry file.json
    python xhtml_tokenizer.py detokenize --input file.tokenized --registry file.json --output file.xhtml
    python xhtml_tokenizer.py validate --original file.tokenized --translated file.translated
"""

import argparse
import json
import os
import re
import sys


# Regex to match XHTML/HTML tags (opening, closing, self-closing)
_TAG_RE = re.compile(r"(<[^>]+>)")

# Regex to extract token patterns from tokenized text
# Tokens look like <em:1>, </em:1>, <br:1/> — XML-style for LLM preservation
_TOKEN_RE = re.compile(
    r"<(/?)([a-zA-Z][a-zA-Z0-9._-]*:\d+)(/?)>"
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_full_xhtml(content: str) -> bool:
    """Check if content looks like a full XHTML document (has <html> or <?xml)."""
    stripped = content.strip()
    return stripped.startswith("<?xml") or stripped.lower().startswith("<html") or "<html " in stripped.lower()


def _extract_body_content(content: str) -> tuple:
    """Extract inner body content from a full XHTML document.

    Returns:
        Tuple of (body_inner_content, prefix, suffix) where prefix is
        everything up to and including <body...>, suffix is </body> and after.
        If no <body> found, returns (content, "", "").
    """
    # Find <body...> opening tag
    body_open_match = re.search(r"<body[^>]*>", content, re.IGNORECASE | re.DOTALL)
    if not body_open_match:
        return content, "", ""

    # Find </body> closing tag
    body_close_match = re.search(r"</body\s*>", content, re.IGNORECASE)
    if not body_close_match:
        return content, "", ""

    prefix = content[:body_open_match.end()]
    suffix = content[body_close_match.start():]
    body_inner = content[body_open_match.end():body_close_match.start()]

    return body_inner, prefix, suffix


def _tag_to_semantic_name(tag_str: str) -> str:
    """Extract a semantic name from an XHTML tag string.

    Examples:
        '<em>'                    -> 'EM'
        '<span class="system">'   -> 'SPAN.system'
        '<div class="stat-box">'  -> 'DIV.stat-box'
        '<br/>'                   -> 'BR'
        '</em>'                   -> 'EM'  (closing tags handled by caller)
        '<img src="x.png"/>'      -> 'IMG'

    Strips namespace prefixes (e.g., 'ns0:div' -> 'DIV').
    """
    # Extract tag name: after '<' or '</', before space, '/', or '>'
    m = re.match(r"</?([A-Za-z][A-Za-z0-9:_.-]*)", tag_str)
    if not m:
        return "UNKNOWN"
    tag_name = m.group(1)

    # Strip namespace prefix
    if ":" in tag_name:
        tag_name = tag_name.split(":")[-1]

    tag_name = tag_name.lower()

    # Extract class attribute if present
    class_match = re.search(r'class\s*=\s*"([^"]*)"', tag_str)
    if not class_match:
        class_match = re.search(r"class\s*=\s*'([^']*)'", tag_str)
    if class_match:
        class_val = class_match.group(1).strip()
        if class_val:
            tag_name = f"{tag_name}.{class_val}"

    return tag_name


def _is_self_closing(tag_str: str) -> bool:
    """Check if a tag is self-closing (ends with />)."""
    return tag_str.rstrip().endswith("/>")


def _is_closing_tag(tag_str: str) -> bool:
    """Check if a tag is a closing tag (starts with </)."""
    return tag_str.lstrip().startswith("</")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def tokenize(xhtml_content: str) -> tuple:
    """Replace XHTML tags with semantic guillemet tokens.

    For full XHTML documents (with <html>, <head>, <body>), only the inner
    content of <body> is tokenized. Structural wrapper tags are excluded.

    Args:
        xhtml_content: XHTML string (fragment or full document).

    Returns:
        Tuple of (tokenized_text, token_registry) where token_registry maps
        token keys to original tag strings.
    """
    registry = {}
    counter = 0

    # Check if this is a full XHTML document
    is_full = _is_full_xhtml(xhtml_content)

    if is_full:
        body_content, prefix, suffix = _extract_body_content(xhtml_content)
        if not prefix and not suffix:
            # No body found, tokenize everything
            content_to_tokenize = xhtml_content
        else:
            content_to_tokenize = body_content
    else:
        content_to_tokenize = xhtml_content
        prefix = ""
        suffix = ""

    # Split content into tags and text segments
    parts = _TAG_RE.split(content_to_tokenize)

    # Track opening tags for pairing with closing tags.
    # Keyed by base element name (e.g., "SPAN") -> list of (semantic_name, counter).
    # Closing tags like </span> don't carry class attributes, so we match by
    # base element name and pop the most recent opening.
    open_stack_by_element = {}

    result_parts = []

    for part in parts:
        if not part:
            continue

        if not _TAG_RE.match(part):
            # Plain text segment
            result_parts.append(part)
            continue

        tag_str = part

        # Skip processing instructions and other non-element tags
        if tag_str.startswith("<?") or tag_str.startswith("<!"):
            result_parts.append(tag_str)
            continue

        semantic_name = _tag_to_semantic_name(tag_str)

        # Extract bare element name (no class suffix) for close-tag matching
        base_element = semantic_name.split(".")[0]

        if _is_closing_tag(tag_str):
            # Closing tag -- find matching open entry by base element name
            if base_element in open_stack_by_element and open_stack_by_element[base_element]:
                open_semantic, matched_counter = open_stack_by_element[base_element].pop()
                close_key = f"/{open_semantic}:{matched_counter}"
                registry[close_key] = tag_str
                result_parts.append(f"</{open_semantic}:{matched_counter}>")
            else:
                # No matching open tag; treat as standalone
                counter += 1
                close_key = f"/{semantic_name}:{counter}"
                registry[close_key] = tag_str
                result_parts.append(f"</{semantic_name}:{counter}>")

        elif _is_self_closing(tag_str):
            # Self-closing tag
            counter += 1
            key = f"{semantic_name}:{counter}"
            registry[key] = tag_str
            result_parts.append(f"<{semantic_name}:{counter}/>")

        else:
            # Opening tag
            counter += 1
            key = f"{semantic_name}:{counter}"
            registry[key] = tag_str
            result_parts.append(f"<{semantic_name}:{counter}>")

            # Track for close-tag matching by base element name
            if base_element not in open_stack_by_element:
                open_stack_by_element[base_element] = []
            open_stack_by_element[base_element].append((semantic_name, counter))

    tokenized = "".join(result_parts)

    # Store XHTML wrapper in registry so detokenize can restore it
    if is_full and (prefix or suffix):
        registry["__xhtml_prefix__"] = prefix
        registry["__xhtml_suffix__"] = suffix

    return tokenized, registry


def detokenize(tokenized_text: str, token_registry: dict) -> str:
    """Restore original XHTML tags from semantic tokens using the registry.

    Tokens not found in the registry are left as-is.

    Args:
        tokenized_text: Text with guillemet tokens.
        token_registry: Dict mapping token keys to original tag strings.

    Returns:
        Restored XHTML string.
    """
    def _replace_token(match):
        slash_prefix = match.group(1)  # '/' for closing tokens, '' otherwise
        key_base = match.group(2)      # e.g., 'EM:1'
        slash_suffix = match.group(3)  # '/' for self-closing tokens, '' otherwise

        if slash_prefix:
            # Closing token: «/EM:1»
            lookup_key = f"/{key_base}"
        elif slash_suffix:
            # Self-closing token: «EM:1/»
            lookup_key = key_base
        else:
            # Opening token: «EM:1»
            lookup_key = key_base

        if lookup_key in token_registry:
            return token_registry[lookup_key]
        else:
            # Token not in registry, leave as-is
            return match.group(0)

    result = _TOKEN_RE.sub(_replace_token, tokenized_text)

    # Restore XHTML wrapper if it was saved during tokenization
    prefix = token_registry.get("__xhtml_prefix__", "")
    suffix = token_registry.get("__xhtml_suffix__", "")
    if prefix or suffix:
        result = prefix + result + suffix

    return result


def validate_tokens(original_text: str, translated_text: str) -> dict:
    """Validate that all tokens are preserved in the translated text.

    Checks for:
    - Missing tokens (in original but not in translated)
    - Extra tokens (in translated but not in original)
    - Unclosed tokens (opening without matching close in translated)

    Args:
        original_text: Tokenized original text.
        translated_text: Tokenized translated text.

    Returns:
        Dict with 'valid' (bool) and 'errors' (list of error strings).
    """
    errors = []

    # Extract all tokens from both texts
    original_tokens = _TOKEN_RE.findall(original_text)
    translated_tokens = _TOKEN_RE.findall(translated_text)

    # Build sets of full token representations
    def _token_set(token_list):
        result = set()
        for slash_prefix, key_base, slash_suffix in token_list:
            if slash_prefix:
                result.add(f"/{key_base}")
            elif slash_suffix:
                result.add(f"{key_base}/")
            else:
                result.add(key_base)
        return result

    orig_set = _token_set(original_tokens)
    trans_set = _token_set(translated_tokens)

    # Check for missing tokens
    for token in orig_set:
        if token not in trans_set:
            clean = token.rstrip("/").lstrip("/")
            if token.startswith("/"):
                errors.append(f"Missing closing token: {clean}")
            elif token.endswith("/"):
                errors.append(f"Missing self-closing token: {clean}")
            else:
                errors.append(f"Missing token: {clean}")

    # Check for extra tokens
    for token in trans_set:
        if token not in orig_set:
            clean = token.rstrip("/").lstrip("/")
            errors.append(f"Extra token: {clean}")

    # Check for unclosed tokens in translated text
    # Build opening/closing pairs
    trans_openings = set()
    trans_closings = set()
    for slash_prefix, key_base, slash_suffix in translated_tokens:
        if slash_prefix:
            trans_closings.add(key_base)
        elif slash_suffix:
            pass  # self-closing, no pair needed
        else:
            trans_openings.add(key_base)

    for opening in trans_openings:
        if opening not in trans_closings:
            # Check if it's supposed to have a closing (was it in the original as paired?)
            if f"/{opening}" in orig_set:
                errors.append(f"Unclosed token: {opening}")

    valid = len(errors) == 0
    return {"valid": valid, "errors": errors}


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _cmd_tokenize(args):
    """Handle the 'tokenize' subcommand."""
    input_path = args.input
    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    tokenized, registry = tokenize(content)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(tokenized)

    with open(args.registry, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def _cmd_detokenize(args):
    """Handle the 'detokenize' subcommand."""
    input_path = args.input
    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    registry_path = args.registry
    if not os.path.isfile(registry_path):
        print(f"Error: Registry file not found: {registry_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        tokenized = f.read()

    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    restored = detokenize(tokenized, registry)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(restored)


def _cmd_validate(args):
    """Handle the 'validate' subcommand."""
    original_path = args.original
    if not os.path.isfile(original_path):
        print(f"Error: Original file not found: {original_path}", file=sys.stderr)
        sys.exit(1)

    translated_path = args.translated
    if not os.path.isfile(translated_path):
        print(f"Error: Translated file not found: {translated_path}", file=sys.stderr)
        sys.exit(1)

    with open(original_path, "r", encoding="utf-8") as f:
        original = f.read()

    with open(translated_path, "r", encoding="utf-8") as f:
        translated = f.read()

    result = validate_tokens(original, translated)
    print(json.dumps(result, indent=2))


def main():
    """CLI entry point with subcommands for XHTML tokenizer."""
    parser = argparse.ArgumentParser(
        description="XHTML tokenizer for CABT translation pipeline."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # tokenize subcommand
    tok = subparsers.add_parser("tokenize", help="Tokenize XHTML tags")
    tok.add_argument("--input", required=True, help="Input XHTML file")
    tok.add_argument("--output", required=True, help="Output tokenized text file")
    tok.add_argument("--registry", required=True, help="Output token registry JSON file")
    tok.set_defaults(func=_cmd_tokenize)

    # detokenize subcommand
    detok = subparsers.add_parser("detokenize", help="Restore XHTML from tokens")
    detok.add_argument("--input", required=True, help="Input tokenized text file")
    detok.add_argument("--registry", required=True, help="Token registry JSON file")
    detok.add_argument("--output", required=True, help="Output XHTML file")
    detok.set_defaults(func=_cmd_detokenize)

    # validate subcommand
    val = subparsers.add_parser("validate", help="Validate token preservation")
    val.add_argument("--original", required=True, help="Original tokenized text file")
    val.add_argument("--translated", required=True, help="Translated tokenized text file")
    val.set_defaults(func=_cmd_validate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
