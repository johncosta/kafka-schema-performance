from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

from benchmark.env import collect_pip_freeze_integrity


def test_collect_pip_freeze_integrity_sorts_and_hashes() -> None:
    proc = MagicMock()
    proc.stdout = "b==1\na==2\n"
    proc.returncode = 0
    with patch("benchmark.env.subprocess.run", return_value=proc):
        r = collect_pip_freeze_integrity()
    assert r["lines"] == ["a==2", "b==1"]
    assert r["line_count"] == 2
    expected = hashlib.sha256(b"a==2\nb==1").hexdigest()
    assert r["sha256"] == expected
    assert r["pip_exit_code"] == 0
