import asyncio
import os
import sys
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config
from deriv_client import DerivClient
from market_data import MarketDataManager
from strategy import MeanReversionStrategy
from risk_manager import RiskManager
from executor import OrderExecutor

# Setup state storage
bot_state: Dict[str, Any] = {
    "account_id": config.DERIV_ACCOUNT_ID,
    "balance": 9930.25,
    "currency": "USD",
    "bot_running": True,
    "quotes": {"R_75": 0.0, "cryBTCUSD": 0.0},
    "positions": {},
    "logs": [f"System initialized. Target assets: Volatility 75 (R_75), Bitcoin (cryBTCUSD)"]
}

def add_log(msg: str):
    import time
    ts = time.strftime("%H:%M:%S")
    bot_state["logs"].append(f"<span class='log-time'>[{ts}]</span> {msg}")
    if len(bot_state["logs"]) > 50:
        bot_state["logs"].pop(0)

class WebTradingBot:
    def __init__(self):
        self.client = DerivClient()
        self.market_data = MarketDataManager(granularity=config.TIMEFRAME_SECONDS)
        self.strategy = MeanReversionStrategy(
            bb_period=config.BB_PERIOD,
            bb_std=config.BB_STD,
            rsi_period=config.RSI_PERIOD,
            rsi_oversold=config.RSI_OVERSOLD,
            rsi_overbought=config.RSI_OVERBOUGHT,
            atr_period=config.ATR_PERIOD,
            sl_atr_mult=config.STOP_LOSS_ATR_MULT,
            tp_atr_mult=config.TAKE_PROFIT_ATR_MULT
        )
        self.risk_manager = RiskManager(initial_balance=10000.0)
        self.executor = OrderExecutor(self.client, self.risk_manager, log_callback=add_log)
        self.running = True

    async def run_loop(self):
        add_log("Connecting to Deriv authenticated WebSocket gateway...")
        connected = await self.client.connect()
        if not connected:
            add_log("Failed to connect to Deriv API. Retrying in 10s...")
            return

        bot_state["balance"] = self.client.balance
        bot_state["currency"] = self.client.currency
        self.risk_manager.update_balance(self.client.balance)
        add_log(f"Connected to Deriv! Active Account: {config.DERIV_ACCOUNT_ID} | Balance: ${self.client.balance:.2f}")

        # Fetch initial history
        for sym_code in config.SYMBOLS.keys():
            candles = await self.client.get_candles(sym_code, count=100, granularity=config.TIMEFRAME_SECONDS)
            if candles:
                self.market_data.initialize_history(sym_code, candles)
                add_log(f"Loaded 100 historical candles for {sym_code}")

        # Tick callback
        async def on_tick(data):
            tick = data.get("tick", {})
            symbol = tick.get("symbol")
            price = float(tick.get("quote", 0.0))
            epoch = int(tick.get("epoch", 0))

            if not symbol or not price:
                return

            bot_state["quotes"][symbol] = price
            candle_closed = self.market_data.update_tick(symbol, price, epoch)

            # Check exits
            await self.executor.check_exits(symbol, price)
            bot_state["positions"] = self.risk_manager.open_positions

            if candle_closed and bot_state["bot_running"]:
                df = self.market_data.get_dataframe(symbol)
                sig_data = self.strategy.evaluate_signal(df)
                sig = sig_data.get("signal")
                rsi = sig_data.get("rsi", 0.0)
                add_log(f"[{symbol}] 15m Candle Closed @ {price:.2f} | Signal: {sig} | RSI: {rsi:.1f}")

                if sig in ["BUY", "SELL"]:
                    add_log(f"TRIGGER: Executing {sig} on {symbol} @ {price:.2f}")
                    await self.executor.execute_trade(symbol, sig_data)
                    bot_state["positions"] = self.risk_manager.open_positions

        # Subscribe to ticks
        for sym_code in config.SYMBOLS.keys():
            await self.client.subscribe_ticks(sym_code, on_tick)

        add_log("Live market subscriptions active. Strategy running 24/7.")
        while self.running:
            await asyncio.sleep(1)

bot_instance = WebTradingBot()
bot_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_task
    add_log("Starting cloud trading engine...")
    bot_task = asyncio.create_task(bot_instance.run_loop())
    yield
    bot_instance.running = False
    if bot_task:
        bot_task.cancel()
    await bot_instance.client.disconnect()

app = FastAPI(lifespan=lifespan)

@app.api_route("/", methods=["GET", "HEAD"])
async def serve_dashboard():
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))

@app.get("/api/status")
async def get_status():
    return JSONResponse(bot_state)

@app.post("/api/start")
async def start_bot():
    bot_state["bot_running"] = True
    add_log("Bot resumed by user via web terminal.")
    return {"status": "started"}

@app.post("/api/pause")
async def pause_bot():
    bot_state["bot_running"] = False
    add_log("Bot paused by user via web terminal.")
    return {"status": "paused"}

@app.api_route("/healthz", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "healthy", "service": "deriv-trading-bot"}
