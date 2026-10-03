"""
Checks of small pure functions in the dashboard JavaScript, run with Node.js when it
is installed (skipped otherwise).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / "helios" / "gui" / "static" / "js" / "app.js"
NODE = shutil.which("node")


def _extract(name: str) -> str:
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(rf"^function {name}\(.*?^}}", src, re.S | re.M)
    assert m, f"{name} not found in app.js"
    return m.group(0)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_timestamp_labels_convert_utc_to_selected_zone():
    """Server stamps 'YYYY-MM-DD HH:MM:SS' are UTC; 18:40 UTC is 00:10 next day in IST (+05:30)."""
    script = _extract("formatTimestampToTimezone") + """
let selectedTimezone = 'Asia/Kolkata';
const out = [formatTimestampToTimezone('2026-10-02 18:40:00'),
             formatTimestampToTimezone('2026-10-02T18:40:00Z')];
selectedTimezone = 'UTC';
out.push(formatTimestampToTimezone('2026-10-02 18:40:00'));
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["10-03 00:10", "10-03 00:10", "10-02 18:40"]
