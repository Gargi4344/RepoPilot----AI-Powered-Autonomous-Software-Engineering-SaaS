import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.coding_agent import (
    MAX_CONSECUTIVE_MALFORMED_REPLIES,
    MAX_REPEATED_IDENTICAL_EDITS,
    CodingAgent,
    CodingAgentError,
    _mutation_signature,
)
from app.agents.file_tools import FileTools, PathGuard
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.ollama_provider import OllamaProvider
from app.models import RiskLevel, Task


def _task() -> Task:
    return Task(
        id="task-1", title="Add a docstring", description="Add a module docstring to a.py",
        priority=3, risk=RiskLevel.low, source="repository-todo",
    )


def _ollama_agent(max_iterations: int = 10, timeout_seconds: int = 60, clock=None) -> CodingAgent:
    provider = OllamaProvider(host="http://localhost:11434", model="test-model")
    kwargs = {"clock": clock} if clock is not None else {}
    return CodingAgent(provider, max_iterations=max_iterations, timeout_seconds=timeout_seconds, **kwargs)


def _patch_client(monkeypatch: pytest.MonkeyPatch, chat: AsyncMock) -> None:
    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            return await chat(**kwargs)

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)


def _no_tool_response(content: str) -> dict:
    return {"message": {"role": "assistant", "content": content, "tool_calls": None}}


def _tool_call_response(name: str, arguments: dict) -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        }
    }


async def _no_tests() -> list[dict]:
    return []


def test_agent_stops_when_model_makes_no_tool_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(return_value=_no_tool_response("Nothing to change here."))
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == 1
    assert result.tool_calls == 0
    assert result.summary == "Nothing to change here."


def test_agent_executes_write_file_then_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("write_file", {"path": "a.py", "content": '"""A module."""\n'}),
            _no_tool_response("Added the docstring."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == 2
    assert result.tool_calls == 1
    assert tools.read_file("a.py") == '"""A module."""\n'


def test_agent_hits_iteration_cap_when_never_stopping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(return_value=_tool_call_response("list_files", {}))
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent(max_iterations=3)
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is False
    assert result.iterations == 3


def test_agent_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(return_value=_tool_call_response("list_files", {}))
    _patch_client(monkeypatch, chat)
    # Inject the clock rather than monkeypatching the stdlib time module -- asyncio's own
    # internals call time.monotonic() an unpredictable number of times, which makes a
    # global patch (and any call-counting against it) unreliable.
    clock_values = iter([0.0, 100.0])
    agent = _ollama_agent(max_iterations=50, timeout_seconds=1, clock=lambda: next(clock_values, 100.0))
    tools = FileTools(PathGuard(tmp_path))

    with pytest.raises(CodingAgentError, match="timed out"):
        asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))


def test_agent_reports_path_guard_violation_as_tool_error_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("write_file", {"path": "../outside.py", "content": "bad"}),
            _no_tool_response("Gave up."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.errors and "escapes the worktree" in result.errors[0]


def test_agent_run_tests_tool_reports_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("run_tests", {}),
            _no_tool_response("Tests are failing."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    async def failing_run_tests() -> list[dict]:
        return [{"tool": "pytest", "exit_code": 1}]

    result = asyncio.run(agent.run(_task(), tools, run_tests=failing_run_tests))

    assert result.finished is True
    assert result.tool_calls == 1


def test_agent_run_tests_tool_surfaces_actual_output_not_just_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: the model previously only saw "pytest: exit 1" from a mid-attempt
    # run_tests call, with no error text -- it had no way to diagnose a real failure and
    # just kept guessing blindly (observed in production: dozens of iterations rewriting
    # the same file with no progress). The actual stdout/stderr must reach the model.
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("run_tests", {}),
            _no_tool_response("Tests are failing."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    async def failing_run_tests() -> list[dict]:
        return [{"tool": "eslint", "exit_code": 2, "stdout": "", "stderr": "Cannot find package '@eslint/js'"}]

    logged: list[str] = []

    async def capture_log(level: str, message: str, data: dict | None) -> None:
        logged.append(message)

    result = asyncio.run(agent.run(_task(), tools, run_tests=failing_run_tests, log=capture_log))

    assert result.finished is True
    assert any("@eslint/js" in message for message in logged)


def test_agent_recovers_a_tool_call_embedded_in_a_prose_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = AsyncMock(
        side_effect=[
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "My apologies for that oversight. Let me correct it and provide the "
                        "proper tool call:\n\n"
                        '```json\n{"name": "write_file", "arguments": {"path": "a.py", '
                        '"content": "x = 1\\n"}}\n```\n'
                    ),
                    "tool_calls": None,
                }
            },
            _no_tool_response("Done."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.tool_calls == 1
    assert tools.read_file("a.py") == "x = 1\n"


def test_agent_recovers_a_bare_json_tool_call_with_no_fence_in_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat = AsyncMock(
        side_effect=[
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "It looks like the str_replace function didn't find the old string in the "
                        "file. Let's try a different approach by creating a new test file for "
                        '`extract.py`. { "name": "write_file", "arguments": { "path": '
                        '"tests/test_extract.py", "content": "# placeholder\\n" } }'
                    ),
                    "tool_calls": None,
                }
            },
            _no_tool_response("Done."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.tool_calls == 1
    assert tools.read_file("tests/test_extract.py") == "# placeholder\n"


def test_agent_recovers_when_model_writes_tool_call_as_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(
        side_effect=[
            {"message": {"role": "assistant", "content": '```json\n{"name": "write_file", '
                         '"arguments": {"path": "a.py", "content": "x = 1\\n"}}\n```', "tool_calls": None}},
            _no_tool_response("Done."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.tool_calls == 1
    assert tools.read_file("a.py") == "x = 1\n"


def test_agent_retries_after_malformed_json_tool_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a real qwen2.5-coder:7b response that botched escaping quotes inside the
    # file content it was writing, producing JSON extract_fallback_tool_calls can't parse.
    # Previously this was silently treated as "the model is done" -- the write never
    # happened, the run failed, and the model never got a chance to correct itself.
    malformed = '{"name": "write_file", "arguments": {"path": "a.py", "content": "print("hi")"}}'
    responses = [
        {"message": {"role": "assistant", "content": malformed, "tool_calls": None}},
        _tool_call_response("write_file", {"path": "a.py", "content": 'print("hi")\n'}),
        _no_tool_response("Done."),
    ]
    # messages is mutated in place across iterations, so a mock's recorded call_args would
    # all end up pointing at the same final list -- snapshot a shallow copy per call instead.
    seen_messages: list[list[dict]] = []

    class FakeClient:
        def __init__(self, host: str) -> None:
            self.host = host

        async def chat(self, **kwargs):
            seen_messages.append(list(kwargs["messages"]))
            return responses[len(seen_messages) - 1]

    monkeypatch.setattr("app.ai.providers.ollama_provider.ollama.AsyncClient", FakeClient)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    logged: list[str] = []

    async def capture_log(level: str, message: str, data: dict | None) -> None:
        logged.append(message)

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests, log=capture_log))

    assert result.finished is True
    assert result.iterations == 3
    assert result.tool_calls == 1
    assert tools.read_file("a.py") == 'print("hi")\n'
    assert any("asking it to retry" in message for message in logged)
    assert any("malformed tool call could not be parsed" in error for error in result.errors)

    retry_message = seen_messages[1][-1]
    assert retry_message["role"] == "user"
    assert "could not be parsed" in retry_message["content"]


def test_agent_gives_up_after_consecutive_malformed_replies_well_before_iteration_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: observed in production -- a model stuck producing the same malformed
    # reply retried 20+ times in a row, burning most of a real 25-iteration budget with no
    # chance of ever succeeding. It should give up after a handful of consecutive failures
    # instead of grinding through the whole budget -- max_iterations here is set well above
    # MAX_CONSECUTIVE_MALFORMED_REPLIES specifically to prove it stops early because of the
    # new cap, not because it happened to run out of iterations.
    malformed = '{"name": "write_file", "arguments": {"path": "a.py", "content": "bad "quote""}}'
    chat = AsyncMock(return_value={"message": {"role": "assistant", "content": malformed, "tool_calls": None}})
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent(max_iterations=25)
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == MAX_CONSECUTIVE_MALFORMED_REPLIES
    assert result.tool_calls == 0
    assert "gave up" in result.summary.lower()
    assert len(result.errors) == MAX_CONSECUTIVE_MALFORMED_REPLIES


def test_agent_consecutive_malformed_counter_resets_after_a_real_tool_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A model that's intermittently making real progress (2 bad replies, then a real call,
    # then 2 more bad replies) should never trip the consecutive-failure cap, since it never
    # actually strings MAX_CONSECUTIVE_MALFORMED_REPLIES bad replies together in a row.
    malformed = '{"name": "write_file", "arguments": {"path": "a.py", "content": "bad "quote""}}'
    responses = [
        {"message": {"role": "assistant", "content": malformed, "tool_calls": None}},
        {"message": {"role": "assistant", "content": malformed, "tool_calls": None}},
        _tool_call_response("list_files", {}),
        {"message": {"role": "assistant", "content": malformed, "tool_calls": None}},
        {"message": {"role": "assistant", "content": malformed, "tool_calls": None}},
        _no_tool_response("Giving up for real this time."),
    ]
    chat = AsyncMock(side_effect=responses)
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == 6
    assert result.summary == "Giving up for real this time."


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("write_file", {"path": "a.py", "content": "x = 1\n"}),
        ("str_replace", {"path": "a.py", "old_str": "x", "new_str": "y"}),
    ],
)
def test_mutation_signature_matches_for_identical_calls(name: str, arguments: dict) -> None:
    assert _mutation_signature(name, arguments) == _mutation_signature(name, dict(arguments))


def test_mutation_signature_differs_for_different_content() -> None:
    a = _mutation_signature("write_file", {"path": "a.py", "content": "x = 1\n"})
    b = _mutation_signature("write_file", {"path": "a.py", "content": "x = 2\n"})
    assert a != b


@pytest.mark.parametrize("name", ["list_files", "read_file", "run_tests"])
def test_mutation_signature_is_none_for_non_mutating_tools(name: str) -> None:
    assert _mutation_signature(name, {}) is None


def test_agent_gives_up_after_repeating_the_identical_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: observed in production -- the model wrote the exact same ~276-byte
    # eslint.config.js 7+ times across several minutes, re-running tests in between each
    # time and seeing the identical (non-blocking, explicitly-marked-not-required-to-fix)
    # failure, without ever varying the edit or moving on to the actual task. Every one of
    # those calls is perfectly valid JSON, so MAX_CONSECUTIVE_MALFORMED_REPLIES never
    # triggers -- this needs its own detection.
    same_write = _tool_call_response("write_file", {"path": "eslint.config.js", "content": "{}"})
    chat = AsyncMock(
        side_effect=[
            same_write,
            _tool_call_response("run_tests", {}),
            same_write,
            _tool_call_response("run_tests", {}),
            same_write,
            _tool_call_response("run_tests", {}),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent(max_iterations=25)
    tools = FileTools(PathGuard(tmp_path))

    logged: list[str] = []

    async def capture_log(level: str, message: str, data: dict | None) -> None:
        logged.append(message)

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests, log=capture_log))

    assert result.finished is True
    assert "eslint.config.js" in result.summary
    assert f"{MAX_REPEATED_IDENTICAL_EDITS} times" in result.summary
    assert any("gave up" in message.lower() and "repeated the same edit" in message for message in logged)
    # Gave up well before the 25-iteration budget -- proves it stopped because of the
    # repetition, not because it happened to run out of iterations.
    assert result.iterations < 10


def test_agent_does_not_give_up_when_edits_genuinely_differ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Same file touched repeatedly, but the content is different each time -- this is normal
    # iterative refinement, not a stuck loop, and must not trip the repeated-edit cap.
    chat = AsyncMock(
        side_effect=[
            _tool_call_response("write_file", {"path": "a.py", "content": "x = 1\n"}),
            _tool_call_response("write_file", {"path": "a.py", "content": "x = 2\n"}),
            _tool_call_response("write_file", {"path": "a.py", "content": "x = 3\n"}),
            _no_tool_response("Done."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == 4
    assert result.summary == "Done."
    assert tools.read_file("a.py") == "x = 3\n"


def test_agent_applies_all_edits_from_a_multi_call_text_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    content = (
        '{"name": "str_replace", "arguments": {"path": "a.py", "old_str": "x = 1", "new_str": "x = 2"}}'
        '{"name": "write_file", "arguments": {"path": "b.py", "content": "y = 1\\n"}}'
    )
    chat = AsyncMock(
        side_effect=[
            {"message": {"role": "assistant", "content": content, "tool_calls": None}},
            _no_tool_response("Done."),
        ]
    )
    _patch_client(monkeypatch, chat)
    agent = _ollama_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.tool_calls == 2
    assert tools.read_file("a.py") == "x = 2\n"
    assert tools.read_file("b.py") == "y = 1\n"


def _gemini_call(name: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(name=name, args=args)


def _gemini_response(text: str = "", function_calls: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(text=text, function_calls=function_calls or [])


def _patch_gemini_client(monkeypatch: pytest.MonkeyPatch, responses: list) -> list:
    """Patches app.ai.providers.gemini_provider.genai.Client with a fake whose
    aio.models.generate_content() replays the given responses in order (GeminiProvider
    makes one stateless call per turn, rebuilding the full contents list from scratch each
    time, rather than a stateful chat session). Returns the list of `contents` args the fake
    was called with, one entry per call, so a test can inspect what was actually sent."""
    calls: list = []
    responses_iter = iter(responses)

    async def _fake_generate_content(*, model, contents, config):
        calls.append(contents)
        return next(responses_iter)

    class FakeModels:
        generate_content = staticmethod(_fake_generate_content)

    class FakeAio:
        def __init__(self) -> None:
            self.models = FakeModels()

    class FakeClient:
        def __init__(self, api_key=None) -> None:
            self.api_key = api_key
            self.aio = FakeAio()

    monkeypatch.setattr("app.ai.providers.gemini_provider.genai.Client", FakeClient)
    return calls


def _gemini_agent(max_iterations: int = 10, timeout_seconds: int = 60) -> CodingAgent:
    provider = GeminiProvider(api_key="fake-key", model="gemini-3.5-flash")
    return CodingAgent(provider, max_iterations=max_iterations, timeout_seconds=timeout_seconds)


def test_gemini_agent_stops_when_model_makes_no_function_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gemini_client(monkeypatch, [_gemini_response(text="Nothing to change here.")])
    agent = _gemini_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == 1
    assert result.tool_calls == 0
    assert result.summary == "Nothing to change here."


def test_gemini_agent_executes_a_function_call_then_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_gemini_client(
        monkeypatch,
        [
            _gemini_response(function_calls=[_gemini_call("write_file", {"path": "a.py", "content": '"""A module."""\n'})]),
            _gemini_response(text="Added the docstring."),
        ],
    )
    agent = _gemini_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.iterations == 2
    assert result.tool_calls == 1
    assert tools.read_file("a.py") == '"""A module."""\n'

    # The second turn's history must include the tool's structured result, not a plain
    # string -- this is what tells the model what actually happened to the file it just wrote.
    second_call_contents = calls[1]
    last_content = second_call_contents[-1]
    assert last_content.role == "user"
    assert last_content.parts[0].function_response.name == "write_file"


def test_gemini_agent_gives_up_after_repeating_the_identical_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    same_call = [_gemini_call("write_file", {"path": "eslint.config.js", "content": "{}"})]
    _patch_gemini_client(
        monkeypatch,
        [
            _gemini_response(function_calls=same_call),
            _gemini_response(function_calls=same_call),
            _gemini_response(function_calls=same_call),
        ],
    )
    agent = _gemini_agent(max_iterations=25)
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert "eslint.config.js" in result.summary
    assert f"{MAX_REPEATED_IDENTICAL_EDITS} times" in result.summary
    # Gave up well before the 25-iteration budget.
    assert result.iterations < 10


def test_gemini_agent_reports_path_guard_violation_as_tool_error_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_gemini_client(
        monkeypatch,
        [
            _gemini_response(function_calls=[_gemini_call("write_file", {"path": "../outside.py", "content": "bad"})]),
            _gemini_response(text="Gave up."),
        ],
    )
    agent = _gemini_agent()
    tools = FileTools(PathGuard(tmp_path))

    result = asyncio.run(agent.run(_task(), tools, run_tests=_no_tests))

    assert result.finished is True
    assert result.errors and "escapes the worktree" in result.errors[0]
