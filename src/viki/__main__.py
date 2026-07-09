import sys
from typing import Any, cast

if sys.platform == "win32":
    stdout = cast(Any, sys.stdout)
    stderr = cast(Any, sys.stderr)
    if stdout.encoding and stdout.encoding.lower() != "utf-8":
        stdout.reconfigure(encoding="utf-8")
    if stderr.encoding and stderr.encoding.lower() != "utf-8":
        stderr.reconfigure(encoding="utf-8")

from viki.cli import run

run()
