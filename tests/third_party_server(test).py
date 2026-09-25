"""
Mock Email Middleware Server — for LOCAL TESTING ONLY.

This simulates the third-party Email Middleware API described in
EmailMiddleware_Documentation-Latest.txt, so SendEmail.py can be
developed and tested against something real before the actual
BASE_URL/credentials are handed over.

It implements both real endpoints:
  POST /auth/login
  POST /email/send

It checks headers and body the same way the real API is documented
to, and returns the same success/error response shapes. No email is
ever actually sent — a matching request just gets logged to the
console and answered with the documented success response.

Run it:
    python mock_email_server.py

It listens on http://127.0.0.1:6000 (deliberately different from
your main.py's port 5500, so you can run both at once).

Point your config/.env at it:
    BASE_URL  = http://127.0.0.1:6000
    APP_NAME  = test-app
    APP_ID    = test-app-id-123
    EMAIL_API_KEY = test-api-key-abc123
    FROM      = test@example.com    (the only "authorized" sender this mock accepts)
"""

import time
import uuid

from flask import Flask, jsonify, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Fake credentials — put these in your real config/.env when testing against
# this server. They mean nothing outside this file.
# ---------------------------------------------------------------------------
FAKE_APP_NAME = "test-app"
FAKE_APP_ID = "test-app-id-123"
FAKE_API_KEY = "test-api-key-abc123"
FAKE_AUTHORIZED_FROM = "test@example.com"

# Recipient addresses that trigger specific simulated outcomes, so you can
# exercise your retry/failure-handling logic on demand instead of waiting
# for a real failure to happen.
TRIGGER_500 = "trigger500@test.com"      # simulates a transient provider failure

# In-memory token store: token -> expiry unix timestamp.
# Deliberately short-lived (60s) so you can actually exercise your
# token-refresh logic during testing instead of waiting a long time.
_issued_tokens = {}
TOKEN_TTL_SECONDS = 60


def _token_is_valid(token):
    expiry = _issued_tokens.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        del _issued_tokens[token]
        return False
    return True


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Request body must be JSON"}), 400

    app_name = data.get("appName")
    app_id = data.get("appId")

    if not app_name or not app_id:
        return jsonify({"message": "appName and appId are required"}), 400

    if app_name != FAKE_APP_NAME or app_id != FAKE_APP_ID:
        return jsonify({"message": "Invalid appName or appId"}), 401

    token = str(uuid.uuid4())
    _issued_tokens[token] = time.time() + TOKEN_TTL_SECONDS
    print(f"[MOCK] Issued token {token[:8]}... (expires in {TOKEN_TTL_SECONDS}s)")

    return jsonify({"token": token}), 200


@app.route("/email/send", methods=["POST"])
def send_email():
    # --- Header checks, same as the documented requirements ---
    api_key = request.headers.get("X-API-KEY")
    auth_header = request.headers.get("Authorization", "")

    if api_key != FAKE_API_KEY:
        return jsonify({"status": "error", "message": "Invalid or missing X-API-KEY header"}), 401

    if not auth_header.startswith("Bearer "):
        return jsonify({
            "status": "error",
            "message": "Missing or malformed Authorization header. Expected 'Bearer <token>'",
        }), 401

    token = auth_header[len("Bearer "):].strip()
    if not _token_is_valid(token):
        return jsonify({"status": "error", "message": "Token is invalid or expired"}), 401

    # --- Body checks ---
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    required_fields = ["from", "to", "subject", "body", "isHtml"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({
            "status": "error",
            "message": f"Missing required field(s): {', '.join(missing)}",
        }), 400

    if not isinstance(data["to"], list) or len(data["to"]) == 0:
        return jsonify({"status": "error", "message": "'to' must be a non-empty array of email addresses"}), 400

    if not isinstance(data["isHtml"], bool):
        return jsonify({"status": "error", "message": "'isHtml' must be a boolean"}), 400

    if data["from"] != FAKE_AUTHORIZED_FROM:
        return jsonify({
            "status": "error",
            "message": f"Sender '{data['from']}' is not an authorized sender",
        }), 400

    if "attachments" in data:
        if not isinstance(data["attachments"], list):
            return jsonify({"status": "error", "message": "'attachments' must be an array"}), 400
        for i, att in enumerate(data["attachments"]):
            for f in ["fileName", "contentType", "base64Content"]:
                if f not in att:
                    return jsonify({"status": "error", "message": f"attachments[{i}] missing '{f}'"}), 400

    # --- Deliberate failure trigger, for testing retry logic on demand ---
    if TRIGGER_500 in data["to"]:
        print(f"[MOCK] Recipient {TRIGGER_500} requested — simulating a 500 provider failure.")
        return jsonify({"status": "error", "message": "Simulated internal server error"}), 500

    # --- Simulate success. Nothing is actually sent anywhere. ---
    body_preview = data["body"][:100] + ("..." if len(data["body"]) > 100 else "")
    print("[MOCK] Would send email:")
    print(f"        From:    {data['from']}")
    print(f"        To:      {data['to']}")
    print(f"        Subject: {data['subject']}")
    print(f"        isHtml:  {data['isHtml']}")
    print(f"        Body:    {body_preview}")

    return jsonify({"status": "success", "message": "Email sent successfully"}), 200


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "Mock Email Middleware server is running.",
        "endpoints": ["POST /auth/login", "POST /email/send"],
        "note": f"Send to '{TRIGGER_500}' to simulate a 500 provider failure on purpose.",
    }), 200


if __name__ == "__main__":
    print("=" * 64)
    print("MOCK EMAIL MIDDLEWARE SERVER")
    print("=" * 64)
    print("Use these in your config/.env when testing against this server:")
    print(f"  BASE_URL      = http://127.0.0.1:6000")
    print(f"  APP_NAME      = {FAKE_APP_NAME}")
    print(f"  APP_ID        = {FAKE_APP_ID}")
    print(f"  EMAIL_API_KEY = {FAKE_API_KEY}")
    print(f"  FROM          = {FAKE_AUTHORIZED_FROM}")
    print("-" * 64)
    print(f"Send to '{TRIGGER_500}' as a recipient to simulate a 500 failure on purpose")
    print(f"(useful for testing your retry logic without waiting for a real failure).")
    print(f"Tokens expire after {TOKEN_TTL_SECONDS}s so you can test refresh logic too.")
    print("=" * 64)
    app.run(debug=True, port=6000)