import pytest

from app.ai.text_tool_calls import (
    extract_embedded_tool_calls,
    extract_fallback_tool_calls,
    looks_like_unparsed_tool_call,
)


@pytest.mark.parametrize(
    "content",
    [
        '{"name": "list_files", "arguments": {"path": "./"}}',
        '```json\n{"name": "list_files", "arguments": {"path": "./"}}\n```',
        '```\n{"name": "list_files", "arguments": {"path": "./"}}\n```',
        '{\n  "name": "list_files",\n  "arguments": {\n    "path": "./"\n  }\n}',
        '[{"name": "list_files", "arguments": {"path": "./"}}]',
    ],
)
def test_extract_fallback_tool_calls_recovers_a_single_json_call(content: str) -> None:
    # Observed real behavior from qwen2.5-coder:7b via Ollama: it sometimes writes the tool
    # call as JSON text instead of populating the API's native tool_calls field.
    calls = extract_fallback_tool_calls(content)

    assert calls == [{"name": "list_files", "arguments": {"path": "./"}}]


def test_extract_fallback_tool_calls_recovers_multiple_concatenated_json_objects() -> None:
    # Regression: observed in production -- the model wrote three JSON tool calls
    # back-to-back with no fence and no separator, in a single response. The old
    # single-object parser silently dropped all three, so the agent gave up thinking it
    # was done -- and none of the intended edits were ever applied.
    content = (
        '{"name": "str_replace", "arguments": {"path": "a.py", "old_str": "x", "new_str": "y"}}'
        '{"name": "str_replace", "arguments": {"path": "b.py", "old_str": "1", "new_str": "2"}}'
        '{"name": "run_tests", "arguments": {}}'
    )

    calls = extract_fallback_tool_calls(content)

    assert [call["name"] for call in calls] == ["str_replace", "str_replace", "run_tests"]
    assert calls[0]["arguments"] == {"path": "a.py", "old_str": "x", "new_str": "y"}
    assert calls[2]["arguments"] == {}


def test_extract_fallback_tool_calls_recovers_multiple_objects_separated_by_whitespace() -> None:
    content = (
        '{"name": "read_file", "arguments": {"path": "a.py"}}\n\n'
        '{"name": "read_file", "arguments": {"path": "b.py"}}'
    )

    calls = extract_fallback_tool_calls(content)

    assert len(calls) == 2
    assert calls[0]["arguments"]["path"] == "a.py"
    assert calls[1]["arguments"]["path"] == "b.py"


@pytest.mark.parametrize(
    "content",
    [
        "",
        "I'm done, no changes needed.",
        "Here's my plan: first I'll read the file, then edit it.",
        '{"not_a_tool_call": true}',
        "{invalid json",
    ],
)
def test_extract_fallback_tool_calls_returns_empty_for_non_tool_call_text(content: str) -> None:
    assert extract_fallback_tool_calls(content) == []


def test_extract_embedded_tool_calls_recovers_a_call_wrapped_in_prose() -> None:
    # Regression: observed real behavior after the model was told a previous reply
    # couldn't be parsed -- it apologized in prose, then gave the corrected call inside a
    # fence. The whole-text checks in extract_fallback_tool_calls never look inside a
    # reply that doesn't start with the fence itself, so this was silently dropped.
    content = (
        "My apologies for that oversight. Let me correct it:\n\n"
        '```json\n{"name": "write_file", "arguments": {"path": "a.py", "content": "x = 1\\n"}}\n```\n'
    )

    calls = extract_embedded_tool_calls(content)

    assert calls == [{"name": "write_file", "arguments": {"path": "a.py", "content": "x = 1\n"}}]


def test_extract_embedded_tool_calls_recovers_multiple_calls_separated_by_prose() -> None:
    content = (
        "First, I'll update the file:\n"
        '```json\n{"name": "str_replace", "arguments": {"path": "a.py", "old_str": "x", "new_str": "y"}}\n```\n'
        "Next, I'll run the tests:\n"
        '```json\n{"name": "run_tests", "arguments": {}}\n```\n'
    )

    calls = extract_embedded_tool_calls(content)

    assert [call["name"] for call in calls] == ["str_replace", "run_tests"]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "I'm done, no changes needed.",
        "Here's my plan: first I'll read the file, then edit it.",
    ],
)
def test_extract_embedded_tool_calls_returns_empty_for_non_tool_call_text(content: str) -> None:
    assert extract_embedded_tool_calls(content) == []


def test_extract_embedded_tool_calls_recovers_a_bare_json_object_with_no_fence_in_prose() -> None:
    # Regression: observed in production -- after a str_replace failed, the model wrote
    # "Let's try a different approach by creating a new test file for `extract.py`." and
    # then dropped a bare {"name": "write_file", ...} object directly into the sentence
    # with no ```json fence at all. Fence-based recovery never looks at unfenced text, so
    # this call was silently dropped and the run failed with "no changes" despite the model
    # having produced a perfectly valid write_file call.
    content = (
        "It looks like the str_replace function didn't find the old string in the file. "
        "Let's try a different approach by creating a new test file for `extract.py`. "
        '{ "name": "write_file", "arguments": { "path": "tests/test_extract.py", '
        '"content": "# placeholder\\n" } }'
    )

    calls = extract_embedded_tool_calls(content)

    assert calls == [
        {"name": "write_file", "arguments": {"path": "tests/test_extract.py", "content": "# placeholder\n"}}
    ]


def test_extract_embedded_tool_calls_recovers_multiple_bare_objects_in_prose() -> None:
    content = (
        'First: { "name": "str_replace", "arguments": { "path": "a.py", "old_str": "x", "new_str": "y" } } '
        'then: { "name": "run_tests", "arguments": {} }'
    )

    calls = extract_embedded_tool_calls(content)

    assert [call["name"] for call in calls] == ["str_replace", "run_tests"]


def test_extract_embedded_tool_calls_ignores_a_brace_that_is_not_valid_json() -> None:
    content = "The config uses a { style block } for grouping, nothing else to report."
    assert extract_embedded_tool_calls(content) == []


def test_looks_like_unparsed_tool_call_detects_a_fence_with_invalid_json_embedded_in_prose() -> None:
    content = "Sorry about that, here's the fix:\n```json\n{not valid json\n```\n"
    assert extract_embedded_tool_calls(content) == []
    assert looks_like_unparsed_tool_call(content) is True


@pytest.mark.parametrize(
    "content",
    [
        '{"name": "write_file", "arguments": {"path": "a.py", "content": "bad "quote""}}',
        "{invalid json",
        '{"not_a_tool_call": true}',
        '```json\n{"name": "write_file"\n```',
        "[1, 2,",
    ],
)
def test_looks_like_unparsed_tool_call_detects_failed_attempts(content: str) -> None:
    assert looks_like_unparsed_tool_call(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "",
        "I'm done, no changes needed.",
        "Here's my plan: first I'll read the file, then edit it.",
    ],
)
def test_looks_like_unparsed_tool_call_ignores_genuine_answers(content: str) -> None:
    assert looks_like_unparsed_tool_call(content) is False
