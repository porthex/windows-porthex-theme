import base64, json, os, re, socket, subprocess, tempfile, threading, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT.parent / "Server" / "Server.ini"
TASKBAR = ROOT.parent / "TaskbarStatus" / "TaskbarStatus.ini"
LOCAL_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "PorthexRainmeter"
STATE = LOCAL_STATE / "server-monitor-state.json"
LOCK = LOCAL_STATE / "server-monitor.lock"
RAINMETER = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Rainmeter" / "Rainmeter.exe"
SSH = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
USER_SETTINGS = ROOT / "UserSettings.inc"

def setting(name, fallback):
    try:
        for line in USER_SETTINGS.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip() or fallback
    except OSError:
        pass
    return fallback

HOST_ALIAS = setting("ServerHost", "hermes-cloud")
HOST = setting("ServerAddress", "hermes-cloud.tailaf56f1.ts.net")
PORT = int(setting("ServerPort", "2222"))
STATUS_INTERVAL = 5.0
RESOURCE_INTERVAL = 10.0
BACKUP_INTERVAL = 300.0
REMOTE = r'''LANG=C; CPU=$(vmstat 1 2 | tail -1 | awk '{print 100-$15}'); MEM=$(free -m | awk '/^Mem:/{printf "%.0f",$3*100/$2}'); DISK=$(df -P / | awk 'NR==2{gsub("%","",$5); print $5}'); UPTIME=$(uptime -p | sed 's/^up //'); APPS=$(docker ps --format '{{.Names}}|{{.Status}}' 2>/dev/null | tr '\n' ';'); printf 'CPU=%s\nMEM=%s\nDISK=%s\nUPTIME=%s\nAPPS=%s\n' "$CPU" "$MEM" "$DISK" "$UPTIME" "$APPS"'''
BACKUP_PROBE = r'''set -uo pipefail
timer="$(systemctl is-active porthex-restic-backup.timer 2>/dev/null || true)"
service="$(systemctl is-active porthex-restic-backup.service 2>/dev/null || true)"
if [ "$service" = activating ] || [ "$service" = active ]; then
  printf 'BACKUP_STATE=BACKING UP\nBACKUP_COLOR=216,210,197,255\nBACKUP_LAST=R2 SNAPSHOT IN PROGRESS\nBACKUP_SCHEDULE=HOURLY\n'
  exit 0
fi
if [ ! -r /etc/restic/porthex-r2.env ] || [ ! -r /etc/restic/porthex-r2.password ]; then
  printf 'BACKUP_STATE=CONFIG ERROR\nBACKUP_COLOR=184,104,88,255\nBACKUP_LAST=LAST --\nBACKUP_SCHEDULE=R2 CONFIG MISSING\n'
  exit 0
fi
if [ "$timer" != active ]; then
  printf 'BACKUP_STATE=DISABLED\nBACKUP_COLOR=184,104,88,255\nBACKUP_LAST=LAST --\nBACKUP_SCHEDULE=TIMER DISABLED\n'
  exit 0
fi
set -a; source /etc/restic/porthex-r2.env; set +a
snapshot="$(timeout 18s restic snapshots --host sv1 --latest 1 --json 2>/dev/null)" || {
  printf 'BACKUP_STATE=FAILED\nBACKUP_COLOR=184,104,88,255\nBACKUP_LAST=LAST UNKNOWN\nBACKUP_SCHEDULE=R2 UNREACHABLE\n'
  exit 0
}
result="$(systemctl show porthex-restic-backup.service -p Result --value 2>/dev/null || true)"
SNAPSHOT="$snapshot" RESULT="$result" python3 - <<'PY'
import json, os
from datetime import datetime, timezone
try:
    rows = json.loads(os.environ.get('SNAPSHOT', '[]'))
    row = max(rows, key=lambda x: x.get('time', ''))
    when = datetime.fromisoformat(row['time'].replace('Z', '+00:00'))
    age_hours = max(0, int((datetime.now(timezone.utc) - when).total_seconds() // 3600))
    age = f'{age_hours}H AGO' if age_hours < 24 else f'{age_hours // 24}D AGO'
    short_id = row.get('short_id') or str(row.get('id', ''))[:8]
    failed = os.environ.get('RESULT') not in ('', 'success')
    stale = age_hours > 3
    state = 'FAILED' if failed else ('STALE' if stale else 'HEALTHY')
    color = '184,104,88,255' if failed else ('218,168,92,255' if stale else '95,210,140,255')
    print(f'BACKUP_STATE={state}')
    print(f'BACKUP_COLOR={color}')
    print(f'BACKUP_LAST=R2 {age} / {short_id}')
    print('BACKUP_SCHEDULE=HOURLY')
except Exception:
    print('BACKUP_STATE=FAILED')
    print('BACKUP_COLOR=184,104,88,255')
    print('BACKUP_LAST=LAST UNKNOWN')
    print('BACKUP_SCHEDULE=NO SNAPSHOT')
PY
'''
BACKUP_REMOTE = "printf '%s' '" + base64.b64encode(BACKUP_PROBE.encode()).decode() + "' | base64 -d | sudo -n bash"
file_lock = threading.Lock()
state_lock = threading.Lock()


def clean(value, limit=64):
    return " ".join(str(value or "").replace("#", " ").replace("=", " ").split())[:limit] or "--"


def replace_keys(path, updates):
    source = path.read_text(encoding="utf-8")
    for key, value in updates.items():
        source, count = re.subn(rf"(?m)^{re.escape(key)}=.*$", lambda _: f"{key}={value}", source)
        if count != 1:
            raise RuntimeError(f"Expected one {key} in {path}, found {count}")
    # Keep the atomic staging file invisible to Rainmeter. A temporary
    # .ini beside the skin can be discovered and activated as a second,
    # stale configuration during refresh.
    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=path.parent)
    os.close(fd)
    Path(temp_name).write_text(source, encoding="utf-8")
    os.replace(temp_name, path)


def refresh(config):
    subprocess.run(
        [str(RAINMETER), "!Refresh", config],
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def record(**updates):
    with state_lock:
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if "last_status_check" in updates:
            history = list(data.get("status_check_history", []))
            history.append(updates["last_status_check"])
            data["status_check_history"] = history[-8:]
        if "last_resource_check" in updates:
            history = list(data.get("resource_check_history", []))
            history.append(updates["last_resource_check"])
            data["resource_check_history"] = history[-8:]
        data.update(updates)
        data["monitor_pid"] = os.getpid()
        fd, temp_name = tempfile.mkstemp(prefix="server-monitor-state-", suffix=".json", dir=STATE.parent)
        os.close(fd)
        Path(temp_name).write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp_name, STATE)


def server_online():
    try:
        with socket.create_connection((HOST, PORT), timeout=2.0):
            return True
    except OSError:
        return False


def collect_resources():
    values = {
        "ServerCpu": "--",
        "ServerMemory": "--",
        "ServerDisk": "--",
        "ServerUptime": "--",
        "AppHermesState": "OFFLINE",
        "AppOpenDesignState": "OFFLINE",
    }
    try:
        result = subprocess.run(
            [str(SSH), "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "-o", "ConnectionAttempts=1", HOST_ALIAS, REMOTE],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return values, False
        remote = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                remote[key] = value
        if not all(remote.get(key, "").strip().isdigit() for key in ("CPU", "MEM", "DISK")):
            return values, False
        apps = remote.get("APPS", "").lower()
        values.update({
            "ServerCpu": clean(remote["CPU"], 3),
            "ServerMemory": clean(remote["MEM"], 3),
            "ServerDisk": clean(remote["DISK"], 3),
            "ServerUptime": clean(remote.get("UPTIME"), 28),
            "AppHermesState": "ONLINE",
            "AppOpenDesignState": "HEALTHY" if "open-design" in apps and "healthy" in apps else ("RUNNING" if "open-design" in apps else "OFFLINE"),
        })
        return values, True
    except Exception:
        return values, False


def collect_backup():
    values = {
        "BackupState": "UNKNOWN",
        "BackupColor": "115,112,106,255",
        "BackupLast": "LAST --",
        "BackupSchedule": "NO BACKUP DATA",
    }
    try:
        result = subprocess.run(
            [str(SSH), "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "-o", "ConnectionAttempts=1", HOST_ALIAS, BACKUP_REMOTE],
            capture_output=True,
            text=True,
            timeout=28,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            return values, False, clean(result.stderr or f"ssh exit {result.returncode}", 120)
        remote = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                remote[key] = clean(value, 40)
        mapping = {
            "BACKUP_STATE": "BackupState",
            "BACKUP_COLOR": "BackupColor",
            "BACKUP_LAST": "BackupLast",
            "BACKUP_SCHEDULE": "BackupSchedule",
        }
        if not all(key in remote for key in mapping):
            return values, False, "incomplete backup response"
        for source, target in mapping.items():
            values[target] = remote[source]
        return values, True, ""
    except Exception as error:
        return values, False, clean(f"{type(error).__name__}: {error}", 120)


def status_loop():
    deadline = time.monotonic()
    last = None
    while True:
        started = time.time()
        online = server_online()
        state = "ONLINE" if online else "OFFLINE"
        color = "95,210,140,255" if online else "154,96,88,255"
        with file_lock:
            replace_keys(SERVER, {"ServerState": state, "ServerColor": color})
            replace_keys(TASKBAR, {"ServerState": state, "ServerColor": color})
        if state != last:
            refresh(r"WindowsPorthexTheme\Server")
            refresh(r"WindowsPorthexTheme\TaskbarStatus")
            last = state
        record(last_status_check=started, last_status_iso=datetime.now().isoformat(timespec="seconds"), online=online, status_interval_seconds=STATUS_INTERVAL)
        deadline += STATUS_INTERVAL
        time.sleep(max(0.05, deadline - time.monotonic()))


def resource_loop():
    deadline = time.monotonic()
    while True:
        started = time.time()
        values, ok = collect_resources()
        with file_lock:
            replace_keys(SERVER, values)
        refresh(r"WindowsPorthexTheme\Server")
        record(last_resource_check=started, last_resource_iso=datetime.now().isoformat(timespec="seconds"), resources_ok=ok, resource_interval_seconds=RESOURCE_INTERVAL)
        deadline += RESOURCE_INTERVAL
        time.sleep(max(0.05, deadline - time.monotonic()))


def backup_loop():
    deadline = time.monotonic()
    while True:
        started = time.time()
        values, ok, error = collect_backup()
        if not ok:
            time.sleep(2)
            values, ok, error = collect_backup()
        with file_lock:
            replace_keys(SERVER, values)
        refresh(r"WindowsPorthexTheme\Server")
        record(
            last_backup_check=started,
            last_backup_iso=datetime.now().isoformat(timespec="seconds"),
            backup_probe_ok=ok,
            backup_state=values["BackupState"],
            backup_error=error,
            backup_interval_seconds=BACKUP_INTERVAL,
        )
        deadline += BACKUP_INTERVAL
        time.sleep(max(0.05, deadline - time.monotonic()))


def acquire_singleton():
    import msvcrt
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK.open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit(0)
    return handle


def main():
    singleton = acquire_singleton()
    record(started_iso=datetime.now().isoformat(timespec="seconds"), status_interval_seconds=STATUS_INTERVAL, resource_interval_seconds=RESOURCE_INTERVAL, backup_interval_seconds=BACKUP_INTERVAL)
    threads = [
        threading.Thread(target=status_loop, name="status-5s", daemon=True),
        threading.Thread(target=resource_loop, name="resources-10s", daemon=True),
        threading.Thread(target=backup_loop, name="backup-300s", daemon=True),
    ]
    for thread in threads:
        thread.start()
    while all(thread.is_alive() for thread in threads):
        time.sleep(1)
    singleton.close()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
