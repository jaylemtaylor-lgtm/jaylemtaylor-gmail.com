import os, csv, io, json, time
import requests
from pythontextnow import Client, ConversationService

# These come from the GitHub secrets you made
USERNAME = os.environ["TEXTNOW_USERNAME"]
SID_COOKIE = os.environ["TEXTNOW_SID_COOKIE"]
SHEET_CSV_URL = os.environ["SHEET_CSV_URL"]

# Log in to TextNow
Client.set_client_config(username=USERNAME, sid_cookie=SID_COOKIE)

STATE_FILE = "sent_state.json"

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
    resp = requests.get(SHEET_CSV_URL, timeout=30)
    resp.raise_for_status()
    data = resp.content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(data))
    return list(reader)

def send_text(to_number, body):
    svc = ConversationService(conversation_phone_numbers=[to_number])
    svc.send_message(message=body)

def main():
    state = load_state()
    rows = fetch_rows()
    processed = 0

    for row in rows:
        row_id = row.get("Timestamp") or json.dumps(row, sort_keys=True)

        if state.get(row_id, {}).get("sent"):
            continue

        name = (row.get("Name") or "").strip()
        phone_raw = (row.get("Phone") or row.get("Phone Number") or "").strip()
        comm = (row.get("Preferred Communication") or row.get("Communication") or "").strip().lower()

        phone = normalize_phone(phone_raw)
        if not phone:
            state[row_id] = {"sent": False, "note": "bad phone", "raw": phone_raw}
            continue

        if comm and "text" not in comm:
            state[row_id] = {"sent": True, "note": "not text preference"}
            continue

        code = "ADP-" + (str(abs(hash(row_id)))[:8])
        body = f"Hey {name or 'there'}, this is A Dreamer Production — your 10% off code is {code}. Expires in 14 days. Reply STOP to opt out."

        try:
            send_text(phone, body)
            state[row_id] = {"sent": True, "phone": phone, "code": code}
            processed += 1
            time.sleep(2)
        except Exception as e:
            state[row_id] = {"sent": False, "error": str(e)}
            time.sleep(1)

    save_state(state)
    print(f"Run complete. Newly processed: {processed}")

if __name__ == "__main__":
    main()
