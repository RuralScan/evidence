"""Verify the agent contract against its immutable method origin."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "submissions"))
from configuration import local_method
from registers import blob, snapshot
from git_snapshot import revision
from .core import digest, require


def verify(root):
    folder = root / "workflows/t4_synthesis"
    pin = json.loads((folder / "contract.lock.json").read_bytes())
    require(
        pin["repository"] == "https://github.com/RuralScan/method.git"
        and pin["path"] == "data-model/agent-t4-contract.json",
        "Unexpected contract origin",
    )
    revision(pin["revision"])
    with TemporaryDirectory() as tmp:
        repo = local_method()
        if repo is None:
            repo = Path(tmp) / "method"
            snapshot(repo, pin["repository"], pin["revision"], ["/data-model/"], None)
        data = blob(repo, pin["revision"], pin["path"])
    require(
        digest(data) == pin["sha256"]
        and data == (folder / "contract.json").read_bytes(),
        "Agent T4 contract differs from pinned method definition",
    )
