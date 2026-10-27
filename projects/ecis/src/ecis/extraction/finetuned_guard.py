"""Watchdog helpers for the QLoRA adapter: compare vs Llama and revert if it degrades."""

from __future__ import annotations

import logging
from typing import Any

from ecis.db.init_db import get_connection, get_threshold, log_agent_action, set_threshold

logger = logging.getLogger(__name__)

DEFAULT_FINETUNED_SKILL_DELTA = 0.05
FINETUNED_READERS = {"finetuned_llm", "llm_finetuned"}


def finetuned_reversion_needed(rolling_skill: float) -> tuple[bool, dict[str, Any]]:
    """True when the fine-tuned adapter underperforms the Llama base by the Scorecard delta."""
    delta = get_threshold("finetuned_skill_delta_min", DEFAULT_FINETUNED_SKILL_DELTA)
    if get_threshold("use_finetuned_adapter", 1.0) < 0.5:
        return False, {}

    if rolling_skill < 0:
        return True, {
            "reason": f"Fine-tuned rolling skill {rolling_skill:.4f} is negative; reverting to Llama",
            "skill_delta_min": delta,
        }

    try:
        from ecis.scoring.scorer import score_by_llm_model

        rows = {r["llm_model"]: r for r in score_by_llm_model()}
    except Exception as exc:
        logger.debug("Could not compare fine-tuned vs Llama: %s", exc)
        return False, {}

    ft = rows.get("finetuned")
    llama = rows.get("llama")
    if not ft or not llama or ft.get("n_samples", 0) < 10 or llama.get("n_samples", 0) < 10:
        return False, {}

    ft_skill = ft.get("skill_score") or 0.0
    llama_skill = llama.get("skill_score") or 0.0
    if ft_skill + delta < llama_skill:
        return True, {
            "reason": (
                f"Fine-tuned skill {ft_skill:.4f} trails Llama {llama_skill:.4f} "
                f"by more than {delta:.4f}; reverting to base adapter"
            ),
            "finetuned_skill": ft_skill,
            "llama_skill": llama_skill,
            "skill_delta_min": delta,
        }
    return False, {}


def revert_finetuned_adapter(details: dict | None = None) -> None:
    """Stop using the QLoRA adapter and drop its triangulator weight."""
    payload = details or {}
    set_threshold("use_finetuned_adapter", 0.0)
    conn = get_connection("agents")
    conn.execute(
        """UPDATE reader_weights SET weight = ?, updated_at = datetime('now')
           WHERE reader_name = ?""",
        (0.05, "llm_finetuned"),
    )
    conn.commit()
    conn.close()
    log_agent_action(
        "watchdog_finetuned_llm",
        str(payload),
        "revert_finetuned",
        "adapter disabled; Llama base restored",
    )


def apply_finetuned_gate(spec: str | None, models: list[str]) -> list[str]:
    """If the watchdog reverted the adapter, map --model finetuned to Llama."""
    from ecis.config.settings import settings

    key = (spec or "").strip().lower()
    if key not in ("finetuned", "ft", "qlora", "llama-ft"):
        return models
    if get_threshold("use_finetuned_adapter", 1.0) >= 0.5:
        return models
    logger.warning("Fine-tuned adapter reverted by watchdog; using Llama 3.1 8B")
    return [settings.llm_llama_model]
