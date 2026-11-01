"""Money-specific operational alerts.

The checks are read-only (they query + log, never mutate financial state), so they can be run
from the scheduler, an ops endpoint, or a CLI without disturbing the ledger or the job queue.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select

from ..models import LedgerEventRow
from . import jobs as J

log = logging.getLogger("chitcircle.alerts.money")

# Money must be conserved: a cycle's ledger amounts must sum to zero. Any non-zero total is an
# imbalance worth alerting on (tolerance kept at 0 minor units intentionally).
LEDGER_IMBALANCE_TOLERANCE_MINOR = 0

# Dead-lettered jobs above this count count as a spike worth alerting on.
DEAD_LETTER_SPIKE_THRESHOLD = 10


def check_ledger_imbalance(session) -> dict:
    """Alert when a cycle's ledger amounts do not sum to zero (money not conserved)."""
    imbalanced = [
        (cycle_id, total)
        for cycle_id, total in session.execute(
            select(LedgerEventRow.cycle_id, func.sum(LedgerEventRow.amount))
            .group_by(LedgerEventRow.cycle_id)
        ).all()
        if abs(total) > LEDGER_IMBALANCE_TOLERANCE_MINOR
    ]
    if imbalanced:
        log.warning("money.ledger_imbalance",
                    extra={"imbalanced_cycles": imbalanced})
    return {"imbalanced_cycles": imbalanced}


def check_dead_letter_spike(session) -> dict:
    """Alert when dead-lettered jobs exceed the threshold."""
    dead = J.dead_letter_count(session)
    spiked = dead > DEAD_LETTER_SPIKE_THRESHOLD
    if spiked:
        log.warning("money.dead_letter_spike", extra={"dead_count": dead})
    return {"dead_count": dead, "spiked": spiked}


def run_money_alerts(session) -> dict:
    """Run every money alert and return a summary."""
    return {
        "ledger_imbalance": check_ledger_imbalance(session),
        "dead_letter_spike": check_dead_letter_spike(session),
    }
