import json, os, re, subprocess, tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT.parent / "Server" / "Server.ini"
TASKBAR = ROOT.parent / "TaskbarStatus" / "TaskbarStatus.ini"
OUT = ROOT / "ServerData.inc"
USER_SETTINGS = ROOT / "UserSettings.inc"
SSH = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"

def setting(name, fallback):
    try:
        for line in USER_SETTINGS.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip() or fallback
    except OSError:
        pass
    return fallback

HOST_ALIAS = setting("ServerHost", "hermes-cloud")
REMOTE = r'''LANG=C; CPU=$(vmstat 1 2 | tail -1 | awk '{print 100-$15}'); MEM=$(free -m | awk '/^Mem:/{printf "%.0f",$3*100/$2}'); DISK=$(df -P / | awk 'NR==2{gsub("%","",$5); print $5}'); UPTIME=$(uptime -p | sed 's/^up //'); printf 'CPU=%s\nMEM=%s\nDISK=%s\nUPTIME=%s\n' "$CPU" "$MEM" "$DISK" "$UPTIME"'''


def clean(value, limit=64):
    return " ".join(str(value or "").replace("#", " ").replace("=", " ").split())[:limit] or "--"


def replace_keys(path, updates):
    source = path.read_text(encoding="utf-8")
    for key, value in updates.items():
        source, count = re.subn(rf"(?m)^{re.escape(key)}=.*$", lambda _: f"{key}={value}", source)
        if count != 1:
            raise RuntimeError(f"Expected one {key} in {path}, found {count}")
    path.write_text(source, encoding="utf-8")


values = {
    "ServerState": "OFFLINE",
    "ServerColor": "154,96,88,255",
    "ServerCpu": "--",
    "ServerMemory": "--",
    "ServerDisk": "--",
    "ServerUptime": "--",
    "AppHermesState": "OFFLINE",
}

try:
    result = subprocess.run(
        [str(SSH), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", HOST_ALIAS, REMOTE],
        capture_output=True,
        text=True,
        timeout=18,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "server unreachable")
    remote = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            remote[key] = value
    for key in ("CPU", "MEM", "DISK"):
        if not remote.get(key, "").strip().isdigit():
            raise RuntimeError(f"Invalid {key} value")
    values.update({
        "ServerState": "ONLINE",
        "ServerColor": "95,210,140,255",
        "ServerCpu": clean(remote["CPU"], 3),
        "ServerMemory": clean(remote["MEM"], 3),
        "ServerDisk": clean(remote["DISK"], 3),
        "ServerUptime": clean(remote.get("UPTIME"), 28),
        "AppHermesState": "ONLINE",
    })
except Exception:
    pass

values["ServerDataUpdated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
text = "".join(f"{key}={value}\n" for key, value in values.items())
fd, tmp = tempfile.mkstemp(prefix="ServerData-", suffix=".inc", dir=ROOT)
os.close(fd)
Path(tmp).write_text(text, encoding="utf-8")
os.replace(tmp, OUT)
replace_keys(SERVER, {key: value for key, value in values.items() if key != "ServerDataUpdated"})
replace_keys(TASKBAR, {"ServerState": values["ServerState"], "ServerColor": values["ServerColor"]})
print(json.dumps({"online": values["ServerState"] == "ONLINE", "updated": values["ServerDataUpdated"]}))
