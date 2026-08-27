from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agents.file_tools import FileTools, PathGuardError
from app.ai.base import AIProvider
from app.ai.types import AIMessage, AIRequest, ToolDefinition
from app.models import Task

LogFn = Callable[[str, str, dict | None], Awaitable[None]]

# A model that's confused enough to write an unparseable "tool call" once often just keeps
# making the same mistake -- observed in production: 20+ consecutive malformed replies in a
# row, burning most of a 25-iteration / 30-minute budget without ever making progress. Capped
# far below max_iterations so a genuinely stuck model gives up in a handful of retries
# instead of grinding through the whole budget; a model that's actually recovering (mixing in
# a real tool call) never gets close to this, since any real tool call resets the counter.
MAX_CONSECUTIVE_MALFORMED_REPLIES = 3
# Distinct from the malformed-reply cap above: every call here is perfectly valid and
# executes successfully -- the model just keeps writing the exact same content to the exact
# same file over and over (observed in production: the same ~276-byte eslint.config.js
# written 7+ times across several minutes, chasing a baseline failure explicitly marked "not
# required to fix"). Nothing about that loop is malformed, so it would otherwise run
# undetected all the way to the iteration cap.
MAX_REPEATED_IDENTICAL_EDITS = 3
_MUTATING_TOOL_KEYS: dict[str, tuple[str, ...]] = {
    "write_file": ("path", "content"),
    "str_replace": ("path", "old_str", "new_str"),
}


def _mutation_signature(name: str, arguments: dict) -> tuple[object, ...] | None:
    """A stable fingerprint for a file-mutating tool call, or None for a non-mutating one
    (list_files/read_file/run_tests) -- those are fine to repeat (re-running tests after
    every edit is completely normal), but the same *edit* repeating verbatim means no
    progress is being made, not that the model is diligently rechecking its work."""
    keys = _MUTATING_TOOL_KEYS.get(name)
    if keys is None:
        return None
    return (name, *(arguments.get(k) for k in keys))


_SYSTEM_PROMPT = """You are a careful software engineer making a small, focused change to an \
existing repository. You can only interact with the repository through the tools provided --
there is no shell access.

Rules:
- Make the smallest change that correctly accomplishes the task. Do not refactor, add \
abstractions, or touch files unrelated to the task.
- Use list_files and read_file to understand the code before editing it.
- Prefer str_replace for small edits to existing files; use write_file for new files or a \
full rewrite.
- Call run_tests after you finish making changes, to check your work.
- When you are done -- changes made and tests checked -- reply with a short plain-text \
summary of what you changed and stop calling tools. Do not call any more tools after that.
"""

TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="list_files",
        description=(
            "List files and directories under a path in the repository (recursive, "
            "skips .git/.venv/node_modules/etc). Use this to explore before editing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the repo root. Defaults to the repo root.",
                }
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="read_file",
        description="Read the full contents of a file in the repository.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path relative to the repo root."}},
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="write_file",
        description=(
            "Create a new file or overwrite an existing file with the given content. "
            "Use for new files or full rewrites; prefer str_replace for small edits."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the repo root."},
                "content": {"type": "string", "description": "The full file content to write."},
            },
            "required": ["path", "content"],
        },
    ),
    ToolDefinition(
        name="str_replace",
        description=(
            "Replace one exact, unique occurrence of old_str with new_str in an existing file. "
            "Fails if old_str appears zero or more than once -- include enough surrounding "
            "context in old_str to make it unique."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to the repo root."},
                "old_str": {"type": "string", "description": "The exact existing text to replace."},
                "new_str": {"type": "string", "description": "The text to replace it with."},
            },
            "required": ["path", "old_str", "new_str"],
        },
    ),
    ToolDefinition(
        name="run_tests",
        description=(
            "Run the repository's own allowlisted test/lint commands. Takes no arguments. "
            "Call this after making changes to check your work."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    ),
]


class CodingAgentError(RuntimeError):
    """Raised when the coding agent cannot make progress (timeout, no response, etc.)."""


@dataclass
class CodingAgentResult:
    iterations: int
    finished: bool  # True if the model stopped calling tools on its own
    summary: str
    tool_calls: int = 0
    errors: list[str] = field(default_factory=list)


class CodingAgent:
    """Runs a manual tool-calling loop against whichever AIProvider is configured, to make a
    small code change for one task. Deliberately has no shell/bash tool -- only file
    read/write/replace and the fixed, argument-less run_tests tool -- so the model can never
    run an arbitrary command, and every file path it touches is checked by a PathGuard before
    any filesystem call. Bounded by a hard iteration cap and wall-clock timeout so a stuck
    model can't loop forever.

    This loop is entirely provider-agnostic: a provider that can't reliably populate its
    native tool-calling response (observed with local Ollama models, which sometimes write a
    tool call as free-form JSON text instead) is expected to recover what it can and report
    the rest via AIResponse.finish_reason == "malformed_tool_call" -- see
    app.ai.providers.ollama_provider and app.ai.text_tool_calls for that recovery. Providers
    with real native tool-calling (Anthropic, Gemini) never produce that finish_reason."""

    def __init__(
        self,
        ai_provider: AIProvider,
        max_iterations: int,
        timeout_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = ai_provider
        self._max_iterations = max_iterations
        self._timeout_seconds = timeout_seconds
        self._clock = clock

    async def run(
        self,
        task: Task,
        tools: FileTools,
        run_tests: Callable[[], Awaitable[list[dict]]],
        failure_context: str | None = None,
        log: LogFn | None = None,
    ) -> CodingAgentResult:
        user_prompt = f"Task: {task.title}\n\n{task.description}"
        if task.affected_files:
            user_prompt += f"\n\nFiles this task is expected to touch: {', '.join(task.affected_files)}"
        if failure_context:
            user_prompt += f"\n\nYour previous attempt left the tests failing:\n{failure_context}"

        messages: list[AIMessage] = [AIMessage(role="user", content=user_prompt)]

        started = self._clock()
        tool_call_count = 0
        errors: list[str] = []
        consecutive_malformed = 0
        last_mutation_signature: tuple[object, ...] | None = None
        repeated_mutation_count = 0

        for iteration in range(1, self._max_iterations + 1):
            if self._clock() - started > self._timeout_seconds:
                raise CodingAgentError(f"Coding agent timed out after {self._timeout_seconds}s")

            response = await self._provider.chat(AIRequest(messages=messages, system_prompt=_SYSTEM_PROMPT, tools=TOOLS))
            messages.append(AIMessage(role="assistant", content=response.text, tool_calls=response.tool_calls or None))

            if response.finish_reason == "malformed_tool_call":
                consecutive_malformed += 1
                errors.append(f"iteration {iteration}: malformed tool call could not be parsed")
                if consecutive_malformed >= MAX_CONSECUTIVE_MALFORMED_REPLIES:
                    summary = (
                        f"Gave up after {consecutive_malformed} consecutive replies that looked like "
                        "tool calls but couldn't be parsed."
                    )
                    if log:
                        await log(
                            "warning",
                            f"Coding agent gave up after {consecutive_malformed} consecutive malformed "
                            "replies in a row",
                            None,
                        )
                    return CodingAgentResult(
                        iterations=iteration, finished=True, summary=summary, tool_calls=tool_call_count, errors=errors
                    )
                if log:
                    await log(
                        "warning",
                        "Model's last reply looked like a tool call but couldn't be parsed -- asking it to retry",
                        {"raw_content": response.text[:500]},
                    )
                messages.append(
                    AIMessage(
                        role="user",
                        content=(
                            "Your last reply looked like an attempt to call a tool as plain text, but it "
                            "could not be parsed as a valid tool call -- either the JSON was malformed "
                            "(a common cause: quotes inside file content not escaped correctly) or it "
                            "didn't match a real tool's arguments. Nothing was executed and no file was "
                            "changed. Please try again: either make a proper tool call, or if you were "
                            "writing file content that contains quotes, make sure every quote and "
                            "backslash inside the JSON string is escaped."
                        ),
                    )
                )
                continue

            if not response.tool_calls:
                summary = response.text.strip()
                if log:
                    await log("info", f"Coding agent finished after {iteration} iteration(s)", None)
                return CodingAgentResult(
                    iterations=iteration, finished=True, summary=summary, tool_calls=tool_call_count, errors=errors
                )

            consecutive_malformed = 0
            gave_up_repeating = False
            for call in response.tool_calls:
                tool_call_count += 1
                result, is_error = await self._execute_tool(call.name, call.arguments, tools, run_tests)
                if is_error:
                    errors.append(f"{call.name}: {result}")
                if log:
                    await log(
                        "warning" if is_error else "info",
                        f"tool {call.name}({call.arguments}) -> {result[:200]}",
                        {"tool": call.name, "arguments": call.arguments, "is_error": is_error},
                    )
                messages.append(AIMessage(role="tool", content=result, tool_call_id=call.id, name=call.name))

                signature = _mutation_signature(call.name, call.arguments)
                if signature is not None:
                    if signature == last_mutation_signature:
                        repeated_mutation_count += 1
                    else:
                        last_mutation_signature = signature
                        repeated_mutation_count = 1
                    if repeated_mutation_count >= MAX_REPEATED_IDENTICAL_EDITS:
                        gave_up_repeating = True
                        break
                    if repeated_mutation_count == 2:
                        messages.append(
                            AIMessage(
                                role="user",
                                content=(
                                    "You just made the exact same edit you already made a moment ago -- "
                                    "it didn't fix anything then, so repeating it verbatim won't either. "
                                    "Try a genuinely different approach, or if this change isn't working, "
                                    "stop and explain what you tried instead of repeating it."
                                ),
                            )
                        )

            if gave_up_repeating:
                edited_path = last_mutation_signature[1] if last_mutation_signature else "a file"
                summary = (
                    f"Gave up after repeating the exact same edit to {edited_path} "
                    f"{repeated_mutation_count} times without making progress."
                )
                if log:
                    await log(
                        "warning",
                        f"Coding agent gave up -- repeated the same edit {repeated_mutation_count} times in a row",
                        None,
                    )
                return CodingAgentResult(
                    iterations=iteration, finished=True, summary=summary, tool_calls=tool_call_count, errors=errors
                )

        if log:
            await log("warning", f"Coding agent hit the {self._max_iterations}-iteration cap", None)
        return CodingAgentResult(
            iterations=self._max_iterations, finished=False, summary="", tool_calls=tool_call_count, errors=errors
        )

    @staticmethod
    async def _execute_tool(
        name: str, arguments: dict, tools: FileTools, run_tests: Callable[[], Awaitable[list[dict]]]
    ) -> tuple[str, bool]:
        try:
            if name == "list_files":
                return tools.list_files(arguments.get("path", ".")), False
            if name == "read_file":
                return tools.read_file(arguments["path"]), False
            if name == "write_file":
                return tools.write_file(arguments["path"], arguments["content"]), False
            if name == "str_replace":
                return tools.str_replace(arguments["path"], arguments["old_str"], arguments["new_str"]), False
            if name == "run_tests":
                # Awaited (not called directly) because the real implementation shells out to a
                # subprocess -- run synchronously it would freeze the whole event loop, including
                # the SSE dashboard feed and any other concurrent run, for the test's duration.
                outcomes = await run_tests()
                if not outcomes:
                    return "No allowlisted test tools detected for this repository.", False
                # Include the actual output, not just the exit code -- without it the model has
                # no way to diagnose a real failure and just keeps guessing blindly (observed in
                # production: dozens of iterations rewriting the same file with no progress).
                # "blocking" (set by the orchestrator against a pre-change baseline) tells the
                # model which failures are actually its responsibility to fix -- a repo-wide
                # pre-existing failure it never touched shouldn't send it chasing an unrelated
                # file. Callers that don't set it (e.g. tests) default to the old all-block
                # behavior.
                parts = []
                any_blocking = False
                for o in outcomes:
                    blocking = o.get("blocking", o["exit_code"] != 0)
                    if o["exit_code"] == 0:
                        parts.append(f"{o['tool']}: exit 0 (passed)")
                        continue
                    output = (o.get("stdout", "") + o.get("stderr", "")).strip()[-1500:]
                    if blocking:
                        any_blocking = True
                        parts.append(f"{o['tool']}: exit {o['exit_code']} (failed -- you must fix this)\n{output}")
                    else:
                        parts.append(
                            f"{o['tool']}: exit {o['exit_code']} (pre-existing failure, unrelated to your "
                            f"task -- not required to fix)\n{output}"
                        )
                return "\n\n".join(parts), any_blocking
            return f"Unknown tool: {name}", True
        except (PathGuardError, FileNotFoundError, NotADirectoryError, ValueError) as exc:
            return str(exc), True
