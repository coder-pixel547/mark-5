import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import time
import logging

logger = logging.getLogger("MarketData")

class MarketDataManager:
    def __init__(self, granularity: int = 900):
        self.granularity = granularity  # 900 seconds = 15 minutes
        self.candles: Dict[str, List[Dict[str, float]]] = {}
        self.current_candle: Dict[str, Dict[str, float]] = {}

    def initialize_history(self, symbol: str, raw_candles: List[Dict[str, Any]]):
        """Loads historical candles into buffer."""
        cleaned = []
        for c in raw_candles:
            cleaned.append({
                "epoch": int(c.get("epoch", 0)),
                "open": float(c.get("open", 0.0)),
                "high": float(c.get("high", 0.0)),
                "low": float(c.get("low", 0.0)),
                "close": float(c.get("close", 0.0)),
            })
        self.candles[symbol] = cleaned
        logger.info(f"Loaded {len(cleaned)} historical candles for {symbol}")

    def update_tick(self, symbol: str, quote: float, epoch: int) -> bool:
        """
        Updates candle buffer with incoming live tick.
        Returns True if a candle just closed (new candle started), triggering strategy evaluation.
        """
        if symbol not in self.candles:
            self.candles[symbol] = []
            
        candle_epoch = (epoch // self.granularity) * self.granularity
        
        # Check if we need to start a new candle
        if symbol not in self.current_candle or self.current_candle[symbol]["epoch"] != candle_epoch:
            candle_closed = False
            if symbol in self.current_candle:
                # Append finished candle to history
                self.candles[symbol].append(self.current_candle[symbol])
                if len(self.candles[symbol]) > 200:
                    self.candles[symbol].pop(0)  # Keep buffer at 200 bars
                candle_closed = True
                
            self.current_candle[symbol] = {
                "epoch": candle_epoch,
                "open": quote,
                "high": quote,
                "low": quote,
                "close": quote
            }
            return candle_closed
        else:
            # Update existing candle
            c = self.current_candle[symbol]
            c["high"] = max(c["high"], quote)
            c["low"] = min(c["low"], quote)
            c["close"] = quote
            return False

    def get_dataframe(self, symbol: str) -> pd.DataFrame:
        """Returns candles as pandas DataFrame with open candle included."""
        bars = list(self.candles.get(symbol, []))
        if symbol in self.current_candle:
            bars.append(self.current_candle[symbol])
        if not bars:
            return pd.DataFrame()
        return pd.DataFrame(bars)
