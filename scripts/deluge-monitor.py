#!/usr/bin/env python3
"""
Deluge Torrent Health Monitor

Connects to Deluge Web UI JSON-RPC API to monitor torrent health,
detect problematic torrents (exe files, stalled, errored), and
provide cleanup actions.

Usage:
    python3 scripts/deluge-monitor.py                    # Full health report
    python3 scripts/deluge-monitor.py --check-exe        # Check for exe files only
    python3 scripts/deluge-monitor.py --stalled          # Show stalled torrents
    python3 scripts/deluge-monitor.py --remove-exe       # Remove torrents containing exe files
    python3 scripts/deluge-monitor.py --cleanup          # Interactive cleanup of problem torrents
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
import http.cookiejar

DELUGE_HOST = "192.168.10.141"
DELUGE_PORT = 8112
DELUGE_PASSWORD = "subterra"
DELUGE_URL = f"http://{DELUGE_HOST}:{DELUGE_PORT}/json"

# File extensions that indicate fake/malicious torrents
BAD_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".scr", ".pif", ".com", ".vbs", ".js", ".wsf"}

# Torrent states
PROBLEM_STATES = {"Error", "Paused"}
STALLED_THRESHOLD_SECS = 3600  # 1 hour with no progress


class DelugeClient:
    def __init__(self, host=DELUGE_HOST, port=DELUGE_PORT, password=DELUGE_PASSWORD):
        self.url = f"http://{host}:{port}/json"
        self.password = password
        self.request_id = 0
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self._connected = False

    def _call(self, method, params=None):
        self.request_id += 1
        payload = json.dumps({
            "method": method,
            "params": params or [],
            "id": self.request_id,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            resp = self.opener.open(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            print(f"\033[0;31mError: Cannot connect to Deluge at {self.url}\033[0m")
            print(f"  {e}")
            print(f"  Is Deluge running on {DELUGE_HOST}?")
            sys.exit(1)

        if data.get("error"):
            err = data["error"]
            print(f"\033[0;31mDeluge API error: {err.get('message', err)}\033[0m")
            sys.exit(1)

        return data.get("result")

    def connect(self):
        result = self._call("auth.login", [self.password])
        if not result:
            print("\033[0;31mAuthentication failed — check DELUGE_PASSWORD\033[0m")
            sys.exit(1)
        self._connected = True

        # Connect to the first available daemon
        hosts = self._call("web.get_hosts")
        if hosts:
            host_id = hosts[0][0]
            self._call("web.connect", [host_id])

    def get_torrents(self):
        fields = [
            "name", "state", "progress", "total_size", "download_payload_rate",
            "upload_payload_rate", "eta", "num_seeds", "num_peers",
            "total_seeds", "total_peers", "time_added", "active_time",
            "seeding_time", "ratio", "save_path", "tracker_host",
            "time_since_transfer", "files",
        ]
        result = self._call("web.update_ui", [fields, {}])
        if not result:
            return {}
        return result.get("torrents", {})

    def get_torrent_files(self, torrent_id):
        result = self._call("web.get_torrent_files", [torrent_id])
        return result

    def remove_torrent(self, torrent_id, remove_data=True):
        return self._call("core.remove_torrent", [torrent_id, remove_data])

    def pause_torrent(self, torrent_id):
        return self._call("core.pause_torrent", [[torrent_id]])


def format_size(size_bytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_speed(speed_bytes):
    if speed_bytes == 0:
        return "-"
    return f"{format_size(speed_bytes)}/s"


def format_eta(seconds):
    if seconds < 0 or seconds > 8640000:  # > 100 days
        return "∞"
    if seconds == 0:
        return "-"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


C_RED = "\033[0;31m"
C_GREEN = "\033[0;32m"
C_YELLOW = "\033[1;33m"
C_BLUE = "\033[0;34m"
C_CYAN = "\033[0;36m"
C_BOLD = "\033[1m"
C_NC = "\033[0m"


def state_color(state):
    colors = {
        "Downloading": C_GREEN,
        "Seeding": C_CYAN,
        "Paused": C_YELLOW,
        "Error": C_RED,
        "Queued": C_BLUE,
        "Checking": C_YELLOW,
        "Moving": C_BLUE,
    }
    return colors.get(state, C_NC)


def collect_files_recursive(file_tree):
    """Walk the Deluge file tree (nested dicts) and yield all file paths."""
    if not file_tree:
        return
    contents = file_tree.get("contents")
    if contents:
        for key, val in contents.items():
            if val.get("type") == "file":
                yield val.get("path", key)
            elif val.get("type") == "dir" or val.get("contents"):
                yield from collect_files_recursive(val)
    # If it's a flat file entry at top level
    if file_tree.get("type") == "file":
        yield file_tree.get("path", "")


def find_bad_files(client, torrent_id):
    """Return list of filenames with suspicious extensions."""
    try:
        file_tree = client.get_torrent_files(torrent_id)
    except Exception:
        return []

    bad_files = []
    for fpath in collect_files_recursive(file_tree):
        ext = "." + fpath.rsplit(".", 1)[-1].lower() if "." in fpath else ""
        if ext in BAD_EXTENSIONS:
            bad_files.append(fpath)
    return bad_files


def print_health_report(client):
    torrents = client.get_torrents()

    if not torrents:
        print(f"\n{C_GREEN}No torrents in Deluge.{C_NC}")
        return

    print(f"\n{C_BOLD}{C_CYAN}{'─' * 80}{C_NC}")
    print(f"{C_BOLD}{C_CYAN}  Deluge Health Report — {len(torrents)} torrents{C_NC}")
    print(f"{C_BOLD}{C_CYAN}{'─' * 80}{C_NC}\n")

    # Categorize
    downloading = []
    seeding = []
    paused = []
    errored = []
    stalled = []
    with_exe = []

    for tid, t in torrents.items():
        state = t.get("state", "Unknown")
        name = t.get("name", "Unknown")
        progress = t.get("progress", 0)
        dl_rate = t.get("download_payload_rate", 0)
        time_since = t.get("time_since_transfer", -1)

        entry = {"id": tid, **t}

        if state == "Error":
            errored.append(entry)
        elif state == "Paused":
            paused.append(entry)
        elif state == "Seeding":
            seeding.append(entry)
        elif state == "Downloading":
            # Check for stalled
            if progress < 100 and dl_rate == 0 and time_since > STALLED_THRESHOLD_SECS:
                stalled.append(entry)
            else:
                downloading.append(entry)
        else:
            downloading.append(entry)

        # Check for exe files
        bad = find_bad_files(client, tid)
        if bad:
            entry["bad_files"] = bad
            with_exe.append(entry)

    # Summary
    print(f"  {C_GREEN}●{C_NC} Downloading: {len(downloading)}")
    print(f"  {C_CYAN}●{C_NC} Seeding:     {len(seeding)}")
    print(f"  {C_YELLOW}●{C_NC} Paused:      {len(paused)}")
    print(f"  {C_RED}●{C_NC} Errored:     {len(errored)}")
    print(f"  {C_YELLOW}●{C_NC} Stalled:     {len(stalled)}")
    print(f"  {C_RED}●{C_NC} Bad files:   {len(with_exe)}")

    # Active downloads
    if downloading:
        print(f"\n{C_BOLD}  Active Downloads:{C_NC}")
        for t in downloading:
            print(f"    {state_color(t['state'])}●{C_NC} {t['name'][:60]}")
            print(f"      {t['progress']:.1f}% | ↓ {format_speed(t.get('download_payload_rate', 0))} | "
                  f"ETA: {format_eta(t.get('eta', 0))} | "
                  f"Seeds: {t.get('num_seeds', 0)}/{t.get('total_seeds', 0)}")

    # Problem torrents
    if errored:
        print(f"\n{C_BOLD}{C_RED}  Errored Torrents:{C_NC}")
        for t in errored:
            print(f"    {C_RED}●{C_NC} {t['name'][:60]}")
            print(f"      {t['progress']:.1f}% | Size: {format_size(t.get('total_size', 0))}")

    if stalled:
        print(f"\n{C_BOLD}{C_YELLOW}  Stalled Torrents (no transfer > 1h):{C_NC}")
        for t in stalled:
            print(f"    {C_YELLOW}●{C_NC} {t['name'][:60]}")
            print(f"      {t['progress']:.1f}% | Seeds: {t.get('num_seeds', 0)}/{t.get('total_seeds', 0)}")

    if with_exe:
        print(f"\n{C_BOLD}{C_RED}  Torrents with Suspicious Files:{C_NC}")
        for t in with_exe:
            print(f"    {C_RED}●{C_NC} {t['name'][:60]}")
            for f in t["bad_files"][:5]:
                print(f"      ⚠ {f}")
            if len(t["bad_files"]) > 5:
                print(f"      ... and {len(t['bad_files']) - 5} more")

    print()


def check_exe_only(client):
    torrents = client.get_torrents()
    found = 0

    print(f"\n{C_BOLD}Scanning {len(torrents)} torrents for suspicious files...{C_NC}\n")

    for tid, t in torrents.items():
        bad = find_bad_files(client, tid)
        if bad:
            found += 1
            print(f"  {C_RED}●{C_NC} {t['name']}")
            for f in bad:
                print(f"    ⚠ {f}")

    if found == 0:
        print(f"  {C_GREEN}No suspicious files found.{C_NC}")
    else:
        print(f"\n  {C_RED}{found} torrent(s) with suspicious files.{C_NC}")
        print(f"  Run with --remove-exe to remove them.")

    print()


def remove_exe_torrents(client):
    torrents = client.get_torrents()
    to_remove = []

    print(f"\n{C_BOLD}Scanning for torrents with suspicious files...{C_NC}\n")

    for tid, t in torrents.items():
        bad = find_bad_files(client, tid)
        if bad:
            to_remove.append((tid, t["name"], bad))
            print(f"  {C_RED}●{C_NC} {t['name']}")
            for f in bad[:3]:
                print(f"    ⚠ {f}")

    if not to_remove:
        print(f"  {C_GREEN}No suspicious torrents found.{C_NC}\n")
        return

    print(f"\n  {C_YELLOW}Will remove {len(to_remove)} torrent(s) and their data.{C_NC}")
    confirm = input("  Proceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    for tid, name, _ in to_remove:
        try:
            client.remove_torrent(tid, remove_data=True)
            print(f"  {C_GREEN}Removed:{C_NC} {name}")
        except Exception as e:
            print(f"  {C_RED}Failed to remove {name}: {e}{C_NC}")

    print()


def show_stalled(client):
    torrents = client.get_torrents()
    stalled = []

    for tid, t in torrents.items():
        if (t.get("state") == "Downloading"
                and t.get("progress", 0) < 100
                and t.get("download_payload_rate", 0) == 0
                and t.get("time_since_transfer", -1) > STALLED_THRESHOLD_SECS):
            stalled.append({"id": tid, **t})

    if not stalled:
        print(f"\n  {C_GREEN}No stalled torrents.{C_NC}\n")
        return

    print(f"\n{C_BOLD}{C_YELLOW}  Stalled Torrents ({len(stalled)}):{C_NC}\n")
    for t in stalled:
        time_since = t.get("time_since_transfer", 0)
        hours = time_since / 3600
        print(f"  {C_YELLOW}●{C_NC} {t['name'][:60]}")
        print(f"    {t['progress']:.1f}% | No transfer for {hours:.1f}h | "
              f"Seeds: {t.get('num_seeds', 0)}/{t.get('total_seeds', 0)}")

    print()


def interactive_cleanup(client):
    torrents = client.get_torrents()
    problems = []

    for tid, t in torrents.items():
        issues = []
        state = t.get("state", "Unknown")
        bad = find_bad_files(client, tid)

        if bad:
            issues.append(f"suspicious files: {', '.join(bad[:3])}")
        if state == "Error":
            issues.append("error state")
        if (state == "Downloading"
                and t.get("progress", 0) < 100
                and t.get("download_payload_rate", 0) == 0
                and t.get("time_since_transfer", -1) > STALLED_THRESHOLD_SECS):
            issues.append("stalled")

        if issues:
            problems.append({"id": tid, "issues": issues, **t})

    if not problems:
        print(f"\n  {C_GREEN}No problem torrents found.{C_NC}\n")
        return

    print(f"\n{C_BOLD}  Interactive Cleanup — {len(problems)} problem torrent(s){C_NC}\n")

    for t in problems:
        print(f"  {C_RED}●{C_NC} {t['name']}")
        print(f"    State: {t.get('state')} | Progress: {t.get('progress', 0):.1f}% | "
              f"Size: {format_size(t.get('total_size', 0))}")
        print(f"    Issues: {'; '.join(t['issues'])}")
        print()

        action = input("    [r]emove+data / [p]ause / [s]kip / [q]uit? ").strip().lower()
        if action == "r":
            client.remove_torrent(t["id"], remove_data=True)
            print(f"    {C_GREEN}Removed.{C_NC}\n")
        elif action == "p":
            client.pause_torrent(t["id"])
            print(f"    {C_YELLOW}Paused.{C_NC}\n")
        elif action == "q":
            print("    Done.")
            return
        else:
            print(f"    Skipped.\n")


def main():
    parser = argparse.ArgumentParser(description="Deluge Torrent Health Monitor")
    parser.add_argument("--host", default=DELUGE_HOST, help="Deluge host IP")
    parser.add_argument("--port", type=int, default=DELUGE_PORT, help="Deluge web UI port")
    parser.add_argument("--password", default=DELUGE_PASSWORD, help="Deluge web password")
    parser.add_argument("--check-exe", action="store_true", help="Check for exe/suspicious files only")
    parser.add_argument("--remove-exe", action="store_true", help="Remove torrents with exe files")
    parser.add_argument("--stalled", action="store_true", help="Show stalled torrents")
    parser.add_argument("--cleanup", action="store_true", help="Interactive cleanup of problem torrents")

    args = parser.parse_args()

    client = DelugeClient(host=args.host, port=args.port, password=args.password)

    print(f"{C_BOLD}{C_CYAN}Connecting to Deluge at {args.host}:{args.port}...{C_NC}")
    client.connect()
    print(f"{C_GREEN}Connected.{C_NC}")

    if args.check_exe:
        check_exe_only(client)
    elif args.remove_exe:
        remove_exe_torrents(client)
    elif args.stalled:
        show_stalled(client)
    elif args.cleanup:
        interactive_cleanup(client)
    else:
        print_health_report(client)


if __name__ == "__main__":
    main()
