"""
Context compression for harness.

When a conversation grows long enough to risk hitting the model's context
window, we summarise the oldest messages into a single compact block and
splice it back into the history.  The most-recent `compress_tail` messages
are always kept verbatim so the agent retains its immediate working context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.llm import LLMClient

# Rough chars-per-token estimate (conservative for code-heavy content)
_CHARS_PER_TOKEN = 3.5

COMPRESSION_SYSTEM_PROMPT = """\
You are a context summariser for an AI coding agent called harness.
You will receive a list of conversation turns (user + assistant messages).
Produce a concise but complete summary that preserves:
- The original task / goal
- Every file that was read, created, or edited (with key details)
- Every command that was run and its outcome
- Any errors encountered and how they were resolved
- The current state of the work (what is done, what is pending)

Write the summary in plain prose. Be dense — omit pleasantries and filler.
"""


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return int(total_chars / _CHARS_PER_TOKEN)


def compress_messages(
    client: "LLMClient",
    messages: list[dict[str, str]],
    tail: int,
) -> list[dict[str, str]]:
    """
    Summarise all but the last `tail` messages into one synthetic user message.
    Returns a new message list: [summary_message, ...tail_messages].
    """
    if len(messages) <= tail:
        return messages

    to_compress = messages[:-tail]
    tail_messages = messages[-tail:]

    # Build a readable transcript for the summariser
    transcript_parts = []
    for m in to_compress:
        role = m.get("role", "user").upper()
        content = m.get("content", "")
        transcript_parts.append(f"[{role}]\n{content}")
    transcript = "\n\n".join(transcript_parts)

    try:
        chunks = list(client.stream(
            system=COMPRESSION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        ))
        summary = "".join(chunks).strip()
    except Exception:
        # If compression itself fails, return the original list unchanged
        return messages

    summary_message: dict[str, str] = {
        "role": "user",
        "content": f"[Compressed Session Summary]\n{summary}",
    }
    return [summary_message] + tail_messages


def maybe_compress(
    client: "LLMClient",
    messages: list[dict[str, str]],
    threshold: int,
    tail: int,
) -> tuple[list[dict[str, str]], bool]:
    """
    Compress `messages` if estimated token count exceeds `threshold`.
    Returns (possibly_compressed_messages, was_compressed).
    """
    if estimate_tokens(messages) < threshold:
        return messages, False
    compressed = compress_messages(client, messages, tail)
    return compressed, True
