import asyncio
import logging
import sys
import os
import time
import pandas as pd
from dotenv import load_dotenv

import config
from deriv_client import DerivClient
from market_data import MarketDataManager
from strategy import MeanReversionStrategy
from risk_manager import RiskManager
from executor import OrderExecutor

# Setup structured console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("BotRunner")

class TradingBot:
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
        self.executor = OrderExecutor(self.client, self.risk_manager)
        self.running = False
        self.last_status_time = 0

    async def start(self):
        self.running = True
        logger.info("==================================================")
        logger.info("       DERIV 24/7 MULTI-ASSET TRADING BOT         ")
        logger.info("   Markets: Volatility 75 (R_75) & BTC (cryBTCUSD)")
        logger.info("   Strategy: Bollinger Bands Mean Reversion + RSI ")
        logger.info("==================================================")

        # 1. Connect to Deriv
        connected = await self.client.connect()
        if not connected:
            logger.error("Could not connect to Deriv. Check network connection or API token.")
            return

        if self.client.is_authorized:
            self.risk_manager.update_balance(self.client.balance)
            logger.info(f"Account Authorized: {self.client.balance:.2f} {self.client.currency}")
        else:
            logger.info("Running in PAPER TRADING simulation mode.")

        # 2. Fetch Initial Candle History
        for sym_code, sym_info in config.SYMBOLS.items():
            logger.info(f"Loading 100 historical candles for {sym_info['name']} ({sym_code})...")
            candles = await self.client.get_candles(sym_code, count=100, granularity=config.TIMEFRAME_SECONDS)
            if candles:
                self.market_data.initialize_history(sym_code, candles)
            else:
                logger.warning(f"Could not load initial history for {sym_code}. Will populate from stream.")

        # 3. Define live tick processor callback
        async def on_tick(data):
            tick = data.get("tick", {})
            symbol = tick.get("symbol")
            price = float(tick.get("quote", 0.0))
            epoch = int(tick.get("epoch", 0))

            if not symbol or not price:
                return

            # A. Update candle buffer
            candle_closed = self.market_data.update_tick(symbol, price, epoch)

            # B. Check existing position exit conditions (Mean Reversion 20 SMA / SL / TP)
            await self.executor.check_exits(symbol, price)

            # C. Evaluate Strategy if a candle closed (or periodically)
            if candle_closed:
                df = self.market_data.get_dataframe(symbol)
                signal_data = self.strategy.evaluate_signal(df)
                signal = signal_data.get("signal")

                logger.info(f"[{symbol}] 15m Candle Closed @ {price:.2f} | Signal: {signal} | RSI: {signal_data.get('rsi', 0):.1f}")

                if signal in ["BUY", "SELL"]:
                    await self.executor.execute_trade(symbol, signal_data)

            # D. Periodic status dashboard every 60 seconds
            now = time.time()
            if now - self.last_status_time > 60:
                self.last_status_time = now
                self.print_dashboard()

        # 4. Subscribe to live tick streams
        for sym_code in config.SYMBOLS.keys():
            await self.client.subscribe_ticks(sym_code, on_tick)

        logger.info("Listening for live market data... Bot active 24/7.")

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.client.disconnect()

    def print_dashboard(self):
        bal = self.client.balance if self.client.is_authorized else self.risk_manager.current_balance
        curr = self.client.currency if self.client.is_authorized else "USD"
        open_trades = len(self.risk_manager.open_positions)
        logger.info(f"[DASHBOARD] Balance: {bal:.2f} {curr} | Open Positions: {open_trades}/{config.MAX_TOTAL_OPEN_TRADES}")
        for s, pos in self.risk_manager.open_positions.items():
            logger.info(f"  -> {s}: {pos['type']} @ {pos['entry_price']:.2f} (SL: {pos['stop_loss']:.2f}, TP: {pos['take_profit']:.2f})")

if __name__ == "__main__":
    bot = TradingBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
