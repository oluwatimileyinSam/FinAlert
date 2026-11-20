import os
import plistlib
import subprocess
import sys
from pathlib import Path


LABEL = "com.perennisfons.finalert.background"


def main():
    if sys.platform != "darwin":
        print("This installer is for macOS.")
        return 1

    project_root = Path(__file__).resolve().parents[2]
    python_path = project_root / ".venv" / "bin" / "python"

    if not python_path.is_file():
        print(f"Virtual environment Python not found: {python_path}")
        return 1

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{LABEL}.plist"

    app_data = Path.home() / "Library" / "Application Support" / "FinAlert"
    app_data.mkdir(parents=True, exist_ok=True)

    job = {
        "Label": LABEL,
        "ProgramArguments": [
            str(python_path),
            "-m",
            "email_monitor.background_runner",
        ],
        "WorkingDirectory": str(project_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(app_data / "launchd.stdout.log"),
        "StandardErrorPath": str(app_data / "launchd.stderr.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
    }

    plist_path.write_bytes(plistlib.dumps(job))
    domain = f"gui/{os.getuid()}"

    subprocess.run(
        ["launchctl", "bootout", domain, str(plist_path)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["launchctl", "enable", f"{domain}/{LABEL}"],
        check=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        check=True,
    )

    print(f"Installed and started the FinAlert background agent: {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
