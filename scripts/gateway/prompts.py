"""Prompts, one per task type, written so the free checks are fair.

Each prompt states the task using policy.json's own description -- the single
source of what a task asks -- then the format rules the matching validator
enforces. If a prompt did not ask for what its check requires, the check would
punish the model for something it was never told.

Three rules exist only to remove that mismatch, each found in a real run:

  - Extraction asks for the string "none" rather than null when the text
    states no value. `required_keys` counts null as missing, so a correct
    "no guidance was given" answer would otherwise fail (extract-004).
  - Summarization forbids converting units, because `numbers_grounded` rejects
    any number absent from the input, and "150 basis points" -> "1.5
    percentage points" is a right answer the check cannot accept (summ-004).
  - Contradiction asks for ONE continuous span from ONE statement. In the
    2026-09-17 run, models quoted both conflicting statements joined together;
    `verdict_with_quote` looks for a contiguous substring, so all three
    escalations that run were false alarms caused by this mismatch.

Nothing here is random: the same request always produces the same prompt.
"""

from __future__ import annotations

from typing import Any


def _label(rule: dict[str, Any], text: str) -> str:
    labels = ", ".join(rule["labels"])
    return (
        f"TASK: {rule['description']}\n\n"
        f"RULES:\n"
        f"- Reply with exactly one of: {labels}\n"
        f"- One word only. No explanation, no punctuation, no formatting.\n\n"
        f"TEXT:\n{text}"
    )


def _verdict(rule: dict[str, Any], text: str) -> str:
    labels = ", ".join(rule["labels"])
    return (
        f"TASK: {rule['description']}\n\n"
        f"RULES:\n"
        f"- Reply with a single JSON object and nothing else.\n"
        f'- "verdict": exactly one of {labels}\n'
        f'- If the verdict is contradiction, "quote" must be ONE continuous '
        f"span copied word for word from a SINGLE statement below. Do not "
        f"join text from both statements, and do not add or remove words.\n"
        f'- Otherwise "quote" may be omitted.\n\n'
        f"STATEMENTS:\n{text}"
    )


def _json(rule: dict[str, Any], text: str, required_keys: list[str] | None) -> str:
    if not required_keys:
        raise ValueError(f"{rule['description']!r} needs required_keys to build a prompt")
    keys = ", ".join(required_keys)
    return (
        f"TASK: {rule['description']}\n\n"
        f"RULES:\n"
        f"- Reply with a single JSON object and nothing else.\n"
        f"- Include exactly these keys: {keys}\n"
        f'- If the text does not state a value, use the string "none". '
        f"Never use null, and never invent a value.\n\n"
        f"TEXT:\n{text}"
    )


def _summary(rule: dict[str, Any], text: str) -> str:
    return (
        f"TASK: {rule['description']}\n\n"
        f"RULES:\n"
        f"- Two or three sentences of plain prose.\n"
        f"- Use only figures that appear in the text, copied exactly.\n"
        f"- Do not convert units, compute new figures, or round.\n\n"
        f"TEXT:\n{text}"
    )


def _rag(rule: dict[str, Any], text: str, context: list[str] | None) -> str:
    if not context:
        raise ValueError(f"{rule['description']!r} needs context passages to build a prompt")
    passages = "\n".join(f"[{i}] {p}" for i, p in enumerate(context))
    return (
        f"TASK: {rule['description']}\n\n"
        f"RULES:\n"
        f"- Answer only from the passages below.\n"
        f"- Cite the passage you used, written as [0], [1], and so on.\n"
        f"- If the passages do not answer the question, say so and cite the "
        f"closest passage.\n\n"
        f"PASSAGES:\n{passages}\n\n"
        f"QUESTION:\n{text}"
    )


def build(rule: dict[str, Any], text: str, *, context: list[str] | None = None,
          required_keys: list[str] | None = None) -> str:
    """Build the prompt for one request, from its policy rule."""
    if rule["validator"] == "cites_context":
        return _rag(rule, text, context)
    if rule["output"] == "label":
        return _label(rule, text)
    if rule["output"] == "verdict":
        return _verdict(rule, text)
    if rule["output"] == "json":
        return _json(rule, text, required_keys)
    if rule["output"] == "prose":
        return _summary(rule, text)
    raise ValueError(f"no prompt for output kind {rule['output']!r}")