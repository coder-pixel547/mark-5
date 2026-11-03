import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

class MeanReversionStrategy:
    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates Bollinger Bands, RSI, and ATR on OHLC candle dataframe."""
        data = df.copy()
        
        # 1. Bollinger Bands
        data["sma20"] = data["close"].rolling(self.bb_period).mean()
        rolling_std = data["close"].rolling(self.bb_period).std()
        data["bb_upper"] = data["sma20"] + (rolling_std * self.bb_std)
        data["bb_lower"] = data["sma20"] - (rolling_std * self.bb_std)
        data["bb_width"] = (data["bb_upper"] - data["bb_lower"]) / (data["sma20"] + 1e-9)
        
        # 2. RSI (14)
        delta = data["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.rsi_period).mean()
        rs = gain / (loss + 1e-9)
        data["rsi"] = 100 - (100 / (1 + rs))
        
        # 3. ATR (14)
        hl = data["high"] - data["low"]
        hc = (data["high"] - data["close"].shift(1)).abs()
        lc = (data["low"] - data["close"].shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        data["atr"] = tr.rolling(self.atr_period).mean()
        
        return data

    def evaluate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyzes the latest completed candle and returns a trading signal.
        Returns: {
            "signal": "BUY" | "SELL" | "EXIT_LONG" | "EXIT_SHORT" | "HOLD",
            "price": float,
            "sma20": float,
            "stop_loss": float,
            "take_profit": float,
            "rsi": float,
            "atr": float
        }
        """
        if len(df) < max(self.bb_period, self.rsi_period, self.atr_period) + 10:
            return {"signal": "HOLD", "reason": "Insufficient candles"}
            
        data = self.calculate_indicators(df)
        last_bar = data.iloc[-1]
        
        price = float(last_bar["close"])
        sma20 = float(last_bar["sma20"])
        upper = float(last_bar["bb_upper"])
        lower = float(last_bar["bb_lower"])
        rsi = float(last_bar["rsi"])
        atr = float(last_bar["atr"])
        
        # Consolidation filter: Band width must not be exploding
        is_consolidating = last_bar["bb_width"] < data["bb_width"].tail(50).median() * 1.3
        
        # Signal checks
        if price <= lower and rsi <= self.rsi_oversold and is_consolidating:
            sl = price - (atr * self.sl_atr_mult)
            tp = price + (atr * self.tp_atr_mult)
            return {
                "signal": "BUY",
                "price": price,
                "sma20": sma20,
                "stop_loss": sl,
                "take_profit": tp,
                "rsi": rsi,
                "atr": atr,
                "reason": f"Oversold bounce: Close ({price:.2f}) <= Lower Band ({lower:.2f}), RSI={rsi:.1f}"
            }
            
        elif price >= upper and rsi >= self.rsi_overbought and is_consolidating:
            sl = price + (atr * self.sl_atr_mult)
            tp = price - (atr * self.tp_atr_mult)
            return {
                "signal": "SELL",
                "price": price,
                "sma20": sma20,
                "stop_loss": sl,
                "take_profit": tp,
                "rsi": rsi,
                "atr": atr,
                "reason": f"Overbought rejection: Close ({price:.2f}) >= Upper Band ({upper:.2f}), RSI={rsi:.1f}"
            }
            
        # Target reached checks (Mean Reversion to 20 SMA)
        return {
            "signal": "HOLD",
            "price": price,
            "sma20": sma20,
            "rsi": rsi,
            "atr": atr,
            "reason": f"No trigger. RSI: {rsi:.1f}, Distance to SMA20: {abs(price - sma20):.2f}"
        }
