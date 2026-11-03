import asyncio
import json
import logging
import urllib.request
from typing import Optional, Dict, Any, Callable, List
import websockets
from websockets.asyncio.client import ClientConnection
import config

logger = logging.getLogger("DerivClient")

class DerivClient:
    def __init__(self, api_token: Optional[str] = None, app_id: Optional[str] = None, account_id: Optional[str] = None):
        self.app_id = app_id or config.DERIV_APP_ID
        self.api_token = api_token or config.DERIV_API_TOKEN
        self.account_id = account_id or config.DERIV_ACCOUNT_ID
        self.ws: Optional[ClientConnection] = None
        self.is_connected = False
        self.is_authorized = False
        self.account_info: Dict[str, Any] = {}
        self.balance: float = 0.0
        self.currency: str = "USD"
        self._req_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._handlers: Dict[str, Callable] = {}
        self._ping_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def get_otp_ws_url(self) -> str:
        """Calls Deriv REST API to generate an authenticated WebSocket URL with OTP."""
        logger.info(f"Authenticating with Deriv REST API for Account {self.account_id}...")
        url = f"{config.DERIV_REST_BASE}/accounts/{self.account_id}/otp"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Deriv-App-ID": self.app_id,
            "User-Agent": "Mozilla/5.0"
        }
        req = urllib.request.Request(url, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            ws_url = data.get("data", {}).get("url")
            if not ws_url:
                raise ValueError(f"Could not retrieve WebSocket OTP URL: {data}")
            return ws_url

    async def connect(self) -> bool:
        """Establishes authenticated WebSocket connection to Deriv."""
        try:
            ws_url = self.get_otp_ws_url()
            logger.info("Connecting to authenticated Deriv Trading WebSocket...")
            self.ws = await websockets.connect(ws_url)
            self.is_connected = True
            self.is_authorized = True
            logger.info("Successfully connected to Deriv WebSocket!")

            # Start background message listener and ping keepalive
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._ping_task = asyncio.create_task(self._ping_loop())

            # Fetch account balance
            res = await self.send_request({"balance": 1, "subscribe": 1})
            bal_data = res.get("balance", {})
            self.balance = float(bal_data.get("balance", 0.0))
            self.currency = bal_data.get("currency", "USD")
            logger.info(f"Account Balance: ${self.balance:.2f} {self.currency}")

            return True
        except Exception as e:
            logger.error(f"Failed to connect to Deriv: {e}")
            self.is_connected = False
            self.is_authorized = False
            return False

    async def _ping_loop(self):
        """Sends a ping every 25 seconds to maintain WebSocket connection."""
        while self.is_connected and self.ws:
            try:
                await asyncio.sleep(25)
                await self.send_request({"ping": 1})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Ping error: {e}")
                break

    async def _listen_loop(self):
        """Listens for incoming messages from the Deriv WebSocket server."""
        while self.is_connected and self.ws:
            try:
                msg_str = await self.ws.recv()
                data = json.loads(msg_str)

                req_id = data.get("req_id")
                if req_id and req_id in self._pending_requests:
                    future = self._pending_requests.pop(req_id)
                    if not future.done():
                        future.set_result(data)

                msg_type = data.get("msg_type")
                if msg_type in self._handlers:
                    await self._handlers[msg_type](data)

            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Deriv WebSocket connection closed.")
                self.is_connected = False
                break
            except Exception as e:
                logger.error(f"Error in listen loop: {e}")
                break

    async def send_request(self, payload: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """Sends a JSON request to Deriv and waits for the correlated response via req_id."""
        if not self.ws or not self.is_connected:
            raise ConnectionError("Not connected to Deriv WebSocket.")

        req_id = self._next_req_id()
        payload["req_id"] = req_id

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[req_id] = future

        await self.ws.send(json.dumps(payload))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise TimeoutError(f"Deriv API request timed out for req_id {req_id}")

    async def get_candles(self, symbol: str, count: int = 100, granularity: int = 900) -> List[Dict[str, Any]]:
        """Fetches historical OHLC candle data for a symbol."""
        res = await self.send_request({
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": "candles",
            "granularity": granularity
        })
        if "error" in res:
            logger.error(f"Error fetching candles for {symbol}: {res['error'].get('message')}")
            return []
        return res.get("candles", [])

    async def subscribe_ticks(self, symbol: str, callback: Callable):
        """Subscribes to live price ticks for an asset."""
        self._handlers["tick"] = callback
        await self.send_request({"ticks": symbol, "subscribe": 1})
        logger.info(f"Subscribed to live tick stream for {symbol}")

    async def disconnect(self):
        """Closes connection gracefully."""
        self.is_connected = False
        if self._ping_task: self._ping_task.cancel()
        if self._listen_task: self._listen_task.cancel()
        if self.ws:
            await self.ws.close()
            logger.info("Deriv WebSocket disconnected.")
