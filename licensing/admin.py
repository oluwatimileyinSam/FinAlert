import argparse
import getpass
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "https://finalert-licensing-api.finalert.workers.dev"


def positive_integer(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Enter a whole number.") from exc

    if number < 1:
        raise argparse.ArgumentTypeError("Enter a number greater than zero.")

    return number


def request_admin_api(path, token, payload=None):
    data = None
    headers = {"Authorization": f"Bearer {token}"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{API_BASE_URL}{path}",
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            details = json.loads(exc.read().decode("utf-8"))
            message = details.get("error", f"HTTP {exc.code}")
        except (ValueError, AttributeError):
            message = f"HTTP {exc.code}"
        raise RuntimeError(f"License service rejected the request: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the license service: {exc.reason}") from exc

    if not isinstance(result, dict):
        raise RuntimeError("The license service returned an unexpected response.")

    if "error" in result:
        raise RuntimeError(f"License service error: {result['error']}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Administer FinAlert license keys."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    issue_parser = commands.add_parser("issue", help="Create a new license key.")
    issue_parser.add_argument(
        "--expires-in-days",
        type=positive_integer,
        help="Optional number of days until the license expires.",
    )

    commands.add_parser("stats", help="Show license and activation counts.")

    revoke_parser = commands.add_parser(
        "revoke",
        help="Revoke a license using its license ID.",
    )
    revoke_parser.add_argument("license_id")

    args = parser.parse_args()
    token = getpass.getpass("License admin token: ").strip()

    if not token:
        parser.error("The admin token cannot be empty.")

    try:
        if args.command == "issue":
            payload = {}
            if args.expires_in_days:
                payload["expires_at"] = (
                    int(time.time()) + args.expires_in_days * 24 * 60 * 60
                )

            result = request_admin_api("/admin/licenses", token, payload)
            print("License created. Save this key; it cannot be retrieved later:")
            print(result["license_key"])
            print(f"License ID: {result['license_id']}")

        elif args.command == "stats":
            result = request_admin_api("/admin/stats", token)
            print(json.dumps(result, indent=2))

        elif args.command == "revoke":
            result = request_admin_api(
                "/admin/licenses/revoke",
                token,
                {"license_id": args.license_id},
            )
            print(f"License status: {result['status']}")

    except (RuntimeError, KeyError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
