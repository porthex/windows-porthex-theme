import os, re, sys, tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HERMES = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "hermes-agent"
sys.path.insert(0, str(HERMES))
OUT = ROOT / "AIAccountsData.inc"
SKIN = ROOT.parent / "AIAccounts" / "AIAccounts.ini"
DUE_RED = "220,85,85,255"
DUE_NORMAL = "129,127,120,210"


def clean(value, limit=72):
    return " ".join(str(value or "").replace("#", " ").replace("=", " ").split())[:limit] or "--"


def mask_email(value):
    text = str(value or "").strip()
    if "@" not in text:
        return text
    local, domain = text.rsplit("@", 1)
    return f"{local[:3]}...@{domain}"


def reset_text(value):
    if not value:
        return "RESET UNKNOWN"
    try:
        dt = datetime.fromtimestamp(float(value), tz=datetime.now().astimezone().tzinfo)
        return "RESET " + dt.strftime("%b %d %H:%M").upper()
    except (TypeError, ValueError, OSError):
        return "RESET UNKNOWN"


def due_color(value, now=None):
    try:
        seconds = float(value) - (datetime.now().timestamp() if now is None else float(now))
    except (TypeError, ValueError):
        return DUE_NORMAL
    return DUE_RED if seconds <= 86400 else DUE_NORMAL


def replace_keys(path, updates):
    source = path.read_text(encoding="utf-8")
    for key, value in updates.items():
        source, count = re.subn(rf"(?m)^{re.escape(key)}=.*$", lambda _: f"{key}={value}", source)
        if count != 1:
            raise RuntimeError(f"Expected one {key} in {path}, found {count}")
    path.write_text(source, encoding="utf-8")


def empty(index):
    return {
        f"Account{index}": f"GPT ACCOUNT {index}",
        f"Plan{index}": "NOT CONNECTED",
        f"Renewal{index}": "BILLING RENEWAL: CHECK CHATGPT",
        f"Usage{index}": "ADD ACCOUNT WITH HERMES AUTH",
        f"UsageAlt{index}": "--",
        f"Remaining{index}": "0",
        f"Color{index}": "154,96,88,255",
        f"DateColor{index}": DUE_NORMAL,
    }


def fetch(entry, pool):
    import httpx
    from hermes_cli.auth import _decode_jwt_claims
    from agent.account_usage import _resolve_codex_usage_url

    if pool._entry_needs_refresh(entry):
        entry = pool._refresh_entry(entry, force=False) or entry
    token = entry.runtime_api_key
    claims = _decode_jwt_claims(token)
    auth = claims.get("https://api.openai.com/auth") or {}
    profile = claims.get("https://api.openai.com/profile") or {}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "codex-cli"}
    account_id = auth.get("chatgpt_account_id") if isinstance(auth, dict) else None
    if account_id:
        headers["ChatGPT-Account-Id"] = str(account_id)
    url = _resolve_codex_usage_url(str(entry.runtime_base_url or ""))
    response = httpx.get(url, headers=headers, timeout=15.0)
    response.raise_for_status()
    payload = response.json() or {}
    windows = payload.get("rate_limit") or {}

    def line(key, label):
        window = windows.get(key) or {}
        used = window.get("used_percent")
        if not isinstance(used, (int, float)):
            return f"{label}: NOT REPORTED"
        return f"{label}: {max(0, round(100 - float(used)))}% LEFT / {reset_text(window.get('reset_at'))}"

    primary = windows.get("primary_window") or {}
    primary_used = primary.get("used_percent")
    remaining = max(0, round(100 - float(primary_used))) if isinstance(primary_used, (int, float)) else 0
    email = profile.get("email") if isinstance(profile, dict) else None
    label = mask_email(email) if email else (entry.label or "CHATGPT ACCOUNT")
    return {
        "label": clean(label, 40),
        "plan": clean(payload.get("plan_type") or (auth.get("chatgpt_plan_type") if isinstance(auth, dict) else None) or "CHATGPT", 24).upper(),
        "primary": f"SESSION LIMIT: {remaining}% REMAINING",
        "reset": reset_text(primary.get("reset_at")),
        "date_color": due_color(primary.get("reset_at")),
        "remaining": str(remaining),
        "secondary": clean(line("secondary_window", "WEEKLY")),
    }


def main():
    from agent.credential_pool import load_pool

    values = {}
    pool = load_pool("openai-codex")
    entries = list(pool._entries)[:2]
    seen_labels = set()
    for index in (1, 2):
        values.update(empty(index))
        if index > len(entries):
            continue
        try:
            data = fetch(entries[index - 1], pool)
            if data["label"].lower() in seen_labels:
                values[f"Plan{index}"] = "DUPLICATE LOGIN"
                values[f"Usage{index}"] = "SIGN IN WITH THE OTHER ACCOUNT"
                continue
            seen_labels.add(data["label"].lower())
            values.update({
                f"Account{index}": data["label"],
                f"Plan{index}": data["plan"],
                f"Renewal{index}": data["reset"],
                f"Usage{index}": data["primary"],
                f"UsageAlt{index}": data["secondary"],
                f"Remaining{index}": data["remaining"],
                f"Color{index}": "95,210,140,255",
                f"DateColor{index}": data["date_color"],
            })
        except Exception:
            values[f"Plan{index}"] = "LIVE DATA ERROR"
            values[f"Usage{index}"] = "REFRESH FAILED"
    values["AIAccountsUpdated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = "".join(f"{key}={clean(value, 100)}\n" for key, value in values.items())
    fd, tmp = tempfile.mkstemp(prefix="AIAccountsData-", suffix=".inc", dir=ROOT)
    os.close(fd)
    Path(tmp).write_text(text, encoding="utf-8")
    os.replace(tmp, OUT)
    replace_keys(SKIN, values)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert clean("a#b=c\nd") == "a b c d"
        assert mask_email("someone@example.com") == "som...@example.com"
        assert reset_text(None) == "RESET UNKNOWN"
        assert due_color(86400, now=0) == DUE_RED
        assert due_color(86401, now=0) == DUE_NORMAL
    else:
        main()
