import json, os, re, tempfile
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "GoogleData.inc"
CALENDAR = ROOT.parent / "Calendar" / "Calendar.ini"
EMAIL = ROOT.parent / "Email" / "Email.ini"
USER_SETTINGS = ROOT / "UserSettings.inc"
LOCAL_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "PorthexRainmeter"

def setting(name, fallback):
    try:
        for line in USER_SETTINGS.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip() or fallback
    except OSError:
        pass
    return fallback

TOKEN = Path(setting("GoogleTokenPath", str(LOCAL_STATE / "google_widget_token.json")))
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
GMAIL_INBOX = "https://mail.google.com/mail/u/0/#inbox"


def clean(value, limit=72):
    text = " ".join(str(value or "").replace("#", " ").replace("=", " ").replace("\r", " ").replace("\n", " ").split())
    return text[:limit] or "-"


def event_start(event):
    value = event.get("start", {})
    value = value.get("dateTime") or value.get("date") or ""
    if not value:
        return "NEXT 7 DAYS"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%a %H:%M")
    except Exception:
        return clean(value, 32)


def sender_label(raw):
    name, address = parseaddr(raw or "")
    if name:
        return clean(name, 36)
    if address:
        return clean(address.split("@", 1)[0], 36)
    return "UNKNOWN SENDER"


def replace_keys(path, updates):
    source = path.read_text(encoding="utf-8")
    for key, value in updates.items():
        source, count = re.subn(rf"(?m)^{re.escape(key)}=.*$", lambda _: f"{key}={value}", source)
        if count != 1:
            raise RuntimeError(f"Expected one {key} in {path}, found {count}")
    path.write_text(source, encoding="utf-8")


values = {
    "GoogleConnected": "0",
    "CalendarStatus": "GOOGLE LOGIN REQUIRED",
    "CalendarDetail": "Complete the Google browser authorization.",
    "EmailStatus": "GOOGLE LOGIN REQUIRED",
}
for index in range(1, 4):
    values[f"Email{index}From"] = "CONNECT GMAIL" if index == 1 else "-"
    values[f"Email{index}Subject"] = "Complete Google browser authorization." if index == 1 else "-"
    values[f"Email{index}Url"] = GMAIL_INBOX

try:
    if not TOKEN.exists():
        raise RuntimeError("Google authorization is not complete")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Google authorization expired")

    calendar = build("calendar", "v3", credentials=creds, cache_discovery=False)
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    events = calendar.events().list(
        calendarId="primary",
        timeMin=datetime.now(timezone.utc).isoformat(),
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])
    message_refs = gmail.users().messages().list(
        userId="me", q="in:inbox", maxResults=3
    ).execute().get("messages", [])

    messages = []
    for ref in message_refs[:3]:
        message = gmail.users().messages().get(
            userId="me",
            id=ref["id"],
            format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()
        headers = {h.get("name", "").lower(): h.get("value", "") for h in message.get("payload", {}).get("headers", [])}
        thread_id = message.get("threadId") or message.get("id")
        messages.append({
            "from": sender_label(headers.get("from")),
            "subject": clean(headers.get("subject") or "NO SUBJECT", 62),
            "url": f"{GMAIL_INBOX}/{thread_id}",
        })

    values["GoogleConnected"] = "1"
    if events:
        values["CalendarStatus"] = clean(events[0].get("summary") or "UNTITLED EVENT", 46)
        values["CalendarDetail"] = clean(event_start(events[0]), 40)
    else:
        values["CalendarStatus"] = "NO UPCOMING EVENTS"
        values["CalendarDetail"] = "Google Calendar connected / next 7 days"
    values["EmailStatus"] = "CONNECTED"
    for index in range(1, 4):
        if index <= len(messages):
            message = messages[index - 1]
            values[f"Email{index}From"] = message["from"]
            values[f"Email{index}Subject"] = message["subject"]
            values[f"Email{index}Url"] = message["url"]
        else:
            values[f"Email{index}From"] = "INBOX"
            values[f"Email{index}Subject"] = "No recent message"
            values[f"Email{index}Url"] = GMAIL_INBOX
except Exception:
    pass

values["GoogleDataUpdated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
text = "".join(f"{key}={value}\n" for key, value in values.items())
fd, tmp = tempfile.mkstemp(prefix="GoogleData-", suffix=".inc", dir=ROOT)
os.close(fd)
Path(tmp).write_text(text, encoding="utf-8")
os.replace(tmp, OUT)
replace_keys(CALENDAR, {
    "CalendarStatus": values["CalendarStatus"],
    "CalendarDetail": values["CalendarDetail"],
})
replace_keys(EMAIL, {
    "EmailStatus": values["EmailStatus"],
    "Email1From": values["Email1From"],
    "Email1Subject": values["Email1Subject"],
    "Email1Url": values["Email1Url"],
    "Email2From": values["Email2From"],
    "Email2Subject": values["Email2Subject"],
    "Email2Url": values["Email2Url"],
    "Email3From": values["Email3From"],
    "Email3Subject": values["Email3Subject"],
    "Email3Url": values["Email3Url"],
})
print(json.dumps({"connected": values["GoogleConnected"] == "1", "messages": sum(1 for i in range(1, 4) if values[f"Email{i}Subject"] not in ("-", "No recent message")), "updated": values["GoogleDataUpdated"]}))
