"""Project-local, repeatable setup. Never installs into the system interpreter."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if sys.version_info < (3, 9):
        print("M10 requires Python 3.9 or newer.", file=sys.stderr)
        return 2
    args = sys.argv[1:]
    skip = "--no-install" in args
    args = [a for a in args if a != "--no-install"]
    python = Path(sys.executable)
    if not skip:
        env = root / ".m10" / "venv"
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.exists():
            subprocess.run([sys.executable, "-m", "venv", str(env)], check=True)
        requirements = root / "requirements-runtime.txt"
        radxa = "radxa" in args
        extra = root / "requirements-radxa.txt"
        digest = hashlib.sha256(requirements.read_bytes() + (extra.read_bytes() if radxa else b"")).hexdigest()
        stamp = env / ".m10-requirements"
        if not stamp.exists() or stamp.read_text().strip() != digest:
            install = [str(python), "-m", "pip", "install", "-r", str(requirements)]
            if radxa:
                install += ["-r", str(extra)]
            subprocess.run(install, check=True)
            stamp.write_text(digest + "\n")
    os.chdir(root)
    os.execv(str(python), [str(python), "-m", "m10_runtime.cli", *args])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print("M10 setup failed. Check network access and Python venv/pip support, then rerun.", file=sys.stderr)
        raise SystemExit(exc.returncode)
