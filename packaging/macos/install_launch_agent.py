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
    app_bundles = [
        Path("/Applications/FinAlert.app"),
        Path.home() / "Applications" / "FinAlert.app",
        project_root / "dist" / "FinAlert.app",
    ]
    app_bundle = next((path for path in app_bundles if path.is_dir()), None)

    if app_bundle is None:
        print("FinAlert.app was not found. Build it or place it in Applications.")
        return 1

    app_executable = app_bundle / "Contents" / "MacOS" / "FinAlert"
    if not app_executable.is_file():
        print(f"FinAlert executable not found: {app_executable}")
        return 1

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{LABEL}.plist"

    app_data = Path.home() / "Library" / "Application Support" / "FinAlert"
    app_data.mkdir(parents=True, exist_ok=True)

    job = {
        "Label": LABEL,
        "ProgramArguments": [
            str(app_executable),
            "--background",
        ],
        "WorkingDirectory": str(app_data),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(app_data / "launchd.stdout.log"),
        "StandardErrorPath": str(app_data / "launchd.stderr.log"),
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
    print(f"Using app bundle: {app_bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
