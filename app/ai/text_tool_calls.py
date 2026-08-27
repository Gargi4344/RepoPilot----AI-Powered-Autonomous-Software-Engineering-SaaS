"""Recovery for models that don't reliably populate a native tool-calling response field.

This is specifically an Ollama/local-small-model quirk -- observed behavior with
qwen2.5-coder:7b is to write a tool call as JSON text instead of using the API's structured
tool_calls field: bare, ```json-fenced, or -- when it wants to make several calls in one
turn -- multiple JSON objects concatenated back-to-back with no separator, or a call buried
inside a larger natural-language reply. Hosted providers with real native tool-calling
(Anthropic, Gemini) have no equivalent need for this, so only OllamaProvider calls into this
module; every other provider adapter can assume tool_calls is authoritative."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^```(?:json)?\s*(.*)```\s*$", re.DOTALL)
_EMBEDDED_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_DECODER = json.JSONDecoder()


def extract_fallback_tool_calls(content: str) -> list[dict]:
    """Recovers tool call(s) when the *entire* reply is (or is meant to be) nothing but a
    tool call: bare JSON, ```-fenced JSON, or several JSON objects concatenated back-to-back.
    A real natural-language answer won't parse as any of these shapes and returns []."""
    if not content:
        return []
    text = content.strip()
    fence_match = _FENCE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()

    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [call for item in data if (call := _as_tool_call(item)) is not None] if isinstance(data, list) else []

    calls: list[dict] = []
    pos, length = 0, len(text)
    while pos < length:
        while pos < length and text[pos] in " \t\r\n":
            pos += 1
        if pos >= length or text[pos] != "{":
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        pos = end
        call = _as_tool_call(obj)
        if call is not None:
            calls.append(call)
    return calls


def _scan_json_objects(text: str) -> list[dict]:
    """Finds every well-formed top-level JSON object anywhere in text, regardless of what
    surrounds it -- unlike the raw_decode loop above, which only walks forward from the very
    start of the string and gives up at the first character that isn't whitespace or '{'.
    Scanning resumes right after each successful decode, and skips forward one character past
    any '{' that doesn't decode (e.g. one that's just prose punctuation), so one bad candidate
    can't block real objects later in the same message."""
    objects: list[dict] = []
    pos, length = 0, len(text)
    while pos < length:
        brace = text.find("{", pos)
        if brace == -1:
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(text, brace)
        except json.JSONDecodeError:
            pos = brace + 1
            continue
        objects.append(obj)
        pos = end
    return objects


def extract_embedded_tool_calls(content: str) -> list[dict]:
    """Recovers tool calls embedded anywhere inside a larger natural-language reply -- as
    opposed to extract_fallback_tool_calls above, which only recognizes a reply that IS, in
    its entirety, a tool call. Two observed real shapes: after being told a previous reply
    couldn't be parsed, the model apologizes in prose and then provides the corrected call
    inside a ```json fence; or, with no fence at all, drops a bare {"name": ...} object
    directly into a sentence."""
    calls: list[dict] = []
    for match in _EMBEDDED_FENCE.finditer(content):
        calls.extend(extract_fallback_tool_calls(match.group(1).strip()))
    if not calls:
        for obj in _scan_json_objects(content):
            call = _as_tool_call(obj)
            if call is not None:
                calls.append(call)
    return calls


def looks_like_unparsed_tool_call(content: str) -> bool:
    """True when a reply appears to be an attempt at a JSON tool call that neither
    extract_fallback_tool_calls nor extract_embedded_tool_calls above could turn into a real
    one. Distinguishing this from a genuine natural-language answer matters: an attempt
    should be fed back to the model as a mistake to correct, not silently treated as "the
    model is done"."""
    if not content:
        return False
    text = content.strip()
    fence_match = _FENCE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()
    if text.startswith(("{", "[")):
        return True
    return bool(_EMBEDDED_FENCE.search(content))


def _as_tool_call(obj: object) -> dict | None:
    if not isinstance(obj, dict) or not isinstance(obj.get("name"), str):
        return None
    arguments = obj.get("arguments") or obj.get("parameters") or {}
    if not isinstance(arguments, dict):
        return None
    return {"name": obj["name"], "arguments": arguments}
