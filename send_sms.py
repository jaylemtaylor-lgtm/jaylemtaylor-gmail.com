import os, csv, io, json, time
import requests
from pythontextnow import Client, ConversationService

# ====== CONFIG YOU CAN EDIT (message + code prefix) ======
CODE_PREFIX = "ADP"  # appears before your code (ADP-XXXXXXX)
MESSAGE_TEMPLATE = (
    "Hey {name}, this is A Dreamer Production. "
    "Your 10% off code is {code}. "
    "Show this at checkout to redeem. "
    "Reply STOP to opt out."
)
# If you want a different message, edit MESSAGE_TEMPLATE above. Keep {name} and {code}.
# =========================================================

# These come from the GitHub secrets you made
USERNAME = os.environ["TEXTNOW_USERNAME"]
SID_COOKIE = os.environ["TEXTNOW_SID_COOKIE"]
SHEET_CSV_URL = os.environ["SHEET_CSV_URL"]

# Log in to TextNow using cookie (no password needed)
Client.set_client_config(username=USERNAME, sid_cookie=SID_COOKIE)

STATE_FILE = "sent_state.json"  # remembers who we already texted

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)

def normalize_phone(raw):
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None

def fetch_rows():
    # download CSV export of Form Responses 1
    resp = requests.get(SHEET_CSV_URL, timeout=30)
    resp.raise_for_status()
    data = resp.content.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(data)))

def send_text(to_number, body):
    ConversationService(conversation_phone_numbers=[to_number]).send_message(message=body)

def build_code(row_id: str) -> str:
    return f"{CODE_PREFIX}-" + (str(abs(hash(row_id)))[:8])

def main():
    state = load_state()
    rows = fetch_rows()
    processed = 0

    for row in rows:
        # Use Timestamp if present; otherwise hash the row
        row_id = row.get("Timestamp") or json.dumps(row, sort_keys=True)

        # skip if already sent
        if state.get(row_id, {}).get("sent"):
            continue

        # Adjust these header names if your sheet is different
        name = (row.get("Name") or row.get("First Name") or "").strip() or "there"
        phone_raw = (row.get("Phone") or row.get("Phone Number") or row.get("Phone number") or "").strip()
        # Optional preference column; delete this block if you want to text everyone
        comm = (row.get("Preferred Communication") or row.get("Communication") or "").strip().lower()

        phone = normalize_phone(phone_raw)
        if not phone:
            state[row_id] = {"sent": False, "note": "bad phone", "raw": phone_raw}
            continue

        if comm and "text" not in comm:
            state[row_id] = {"sent": True, "note": "not text preference"}
            continue

        code = build_code(row_id)
        body = MESSAGE_TEMPLATE.format(name=name, code=code)

        try:
            send_text(phone, body)
            state[row_id] = {"sent": True, "phone": phone, "code": code}
            processed += 1
            time.sleep(2)  # gentle pacing
        except Exception as e:
            # Leave as sent=False so it'll retry next run
            state[row_id] = {"sent": False, "error": str(e)}
            time.sleep(1)

    save_state(state)
    print(f"Run complete. Newly processed: {processed}")

if __name__ == "__main__":
    main()
