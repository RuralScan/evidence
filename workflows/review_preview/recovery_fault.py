"""Inject one caught installation failure inside the disposable review checkout."""

import os
from pathlib import Path
from unittest.mock import patch

from preview import EV, HISTORY, LOG, PENDING, read_copy, require

RECORDS = (EV, LOG, HISTORY)
SAVED = tuple(f"pipeline/review/{name}" for name in PENDING)


class RehearsalInterruption(OSError):
    """Raised after a replacement reaches its destination."""


def interrupt_replay(root, replay_call=None):
    if replay_call is None:
        from nbs_ruralscan.schema_tools.submit_review import replay as replay_call

    root = Path(root).resolve(strict=True)
    before = {name: read_copy(root, name) for name in (*RECORDS, *SAVED)}
    destinations = {root / name: name for name in RECORDS}
    replace = os.replace
    interrupted = False

    def replace_then_interrupt(source, destination, **kwargs):
        nonlocal interrupted
        replace(source, destination, **kwargs)
        name = destinations.get(Path(destination))
        if not interrupted and name and read_copy(root, name) != before[name]:
            interrupted = True
            raise RehearsalInterruption(
                "Interrupted after installing a changed review record"
            )

    with patch.object(os, "replace", replace_then_interrupt):
        try:
            replay_call(root)
        except RehearsalInterruption:
            require(interrupted, "Interruption occurred outside the rehearsal")
        else:
            require(not interrupted, "Replay suppressed the installation failure")
    for name, data in before.items():
        require(
            read_copy(root, name) == data,
            f"Rollback differs from the starting record: {name}",
        )
    return interrupted
