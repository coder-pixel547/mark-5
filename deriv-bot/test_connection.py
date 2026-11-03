import asyncio
import json
import os
import urllib.request
from dotenv import load_dotenv
import websockets

load_dotenv()

DERIV_APP_ID = os.getenv("DERIV_APP_ID", "34RboqpEHbA165Ak2BIHZ")
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "").strip()
DERIV_ACCOUNT_ID = os.getenv("DERIV_ACCOUNT_ID", "DOT94309357").strip()
REST_BASE = "https://api.derivws.com/trading/v1/options"

def verify_rest_accounts():
    print("=" * 65)
    print("           DERIV ACCOUNT & CREDENTIAL VERIFICATION           ")
    print("=" * 65)
    print(f"App ID     : {DERIV_APP_ID}")
    print(f"PAT Token  : {DERIV_API_TOKEN[:4]}...{DERIV_API_TOKEN[-6:]}")
    print(f"Account ID : {DERIV_ACCOUNT_ID}")
    print("\n1. Verifying credentials with Deriv REST API...")

    url = f"{REST_BASE}/accounts"
    headers = {
        "Authorization": f"Bearer {DERIV_API_TOKEN}",
        "Deriv-App-ID": DERIV_APP_ID,
        "User-Agent": "Mozilla/5.0"
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            accounts = data.get("data", [])
            print(f"[OK] Deriv API Authentication Successful! ({len(accounts)} accounts found)")
            for acc in accounts:
                print(f"     -> [{acc.get('account_type', '').upper()}] ID: {acc.get('account_id')} | Balance: ${acc.get('balance')} {acc.get('currency')} | Status: {acc.get('status')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[X] Authentication Error {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"[X] Connection Error: {e}")
        return False

async def verify_websocket_stream():
    print("\n2. Requesting WebSocket OTP for Demo trading...")
    url = f"{REST_BASE}/accounts/{DERIV_ACCOUNT_ID}/otp"
    headers = {
        "Authorization": f"Bearer {DERIV_API_TOKEN}",
        "Deriv-App-ID": DERIV_APP_ID,
        "User-Agent": "Mozilla/5.0"
    }
    req = urllib.request.Request(url, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            ws_url = data.get("data", {}).get("url")
            print(f"[OK] One-Time Password Issued! Secure WS URL generated.")

        print(f"\n3. Connecting to Deriv Trading WebSocket...")
        async with websockets.connect(ws_url) as ws:
            print("[OK] Connected to live Deriv Trading WebSocket successfully!")

            # Ping
            await ws.send(json.dumps({"ping": 1}))
            ping_res = json.loads(await ws.recv())
            print(f"[OK] Gateway Heartbeat: {ping_res.get('ping', '').upper()}")

            # Balance
            await ws.send(json.dumps({"balance": 1}))
            bal_res = json.loads(await ws.recv())
            bal = bal_res.get("balance", {})
            print(f"[OK] Live Trading Balance: ${bal.get('balance')} {bal.get('currency')}")

            # Check Volatility 75
            print("\n4. Streaming live market quotes...")
            await ws.send(json.dumps({"ticks": "R_75"}))
            v75_res = json.loads(await ws.recv())
            v75_quote = v75_res.get("tick", {}).get("quote")
            print(f"[OK] Live Volatility 75 (R_75) Quote: {v75_quote}")

            # Check Bitcoin
            await ws.send(json.dumps({"ticks": "cryBTCUSD"}))
            btc_res = json.loads(await ws.recv())
            btc_quote = btc_res.get("tick", {}).get("quote")
            print(f"[OK] Live Bitcoin (cryBTCUSD) Quote: ${btc_quote}")

            print("\n" + "=" * 65)
            print("  ALL SYSTEMS OPERATIONAL! READY TO RUN THE TRADING BOT! ")
            print("=" * 65)

    except Exception as e:
        print(f"[X] WebSocket Error: {e}")

if __name__ == "__main__":
    if verify_rest_accounts():
        asyncio.run(verify_websocket_stream())
