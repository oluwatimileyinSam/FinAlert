import configparser
import os
import sys
from pathlib import Path


APP_NAME = "FinAlert"
PROJECT_ROOT = Path(__file__).resolve().parent


def application_data_directory():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME

    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def configuration_directory():
    if getattr(sys, "frozen", False):
        return application_data_directory()
    return PROJECT_ROOT


CONFIG_DIRECTORY = configuration_directory()
CONFIG_PATH = CONFIG_DIRECTORY / "fin_alert.ini"
ENV_PATH = CONFIG_DIRECTORY / ".env"


def load_local_env():
    """Read simple KEY=value settings from the local .env file."""
    values = {}

    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if key:
            values[key] = value

    return values


def microsoft_settings():
    """Return the Microsoft client ID and authority from local settings."""
    env_values = load_local_env()
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(CONFIG_PATH, encoding="utf-8")

    client_id = (
        os.environ.get("MICROSOFT_CLIENT_ID")
        or env_values.get("MICROSOFT_CLIENT_ID")
        or ini.get("Microsoft", "CLIENT_ID", fallback="")
    ).strip()

    authority = (
        os.environ.get("MICROSOFT_AUTHORITY")
        or env_values.get("MICROSOFT_AUTHORITY")
        or ini.get(
            "Microsoft",
            "AUTHORITY",
            fallback="https://login.microsoftonline.com/common",
        )
    ).strip()

    return client_id, authority


def scan_interval_seconds(default=60):
    """Return the configured scan interval, bounded from 15 to 3600 seconds."""
    env_values = load_local_env()
    raw_value = (
        os.environ.get("FINALERT_SCAN_INTERVAL_SECONDS")
        or env_values.get("FINALERT_SCAN_INTERVAL_SECONDS")
        or str(default)
    )

    try:
        interval = int(raw_value)
    except ValueError:
        return default

    if not 15 <= interval <= 3600:
        return default

    return interval
