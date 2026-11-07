import os
from dotenv import load_dotenv

# Ensure .env is always loaded from the bot's own folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Deriv API Settings
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "34RboqpEHbA165Ak2BIHZ")
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
DERIV_ACCOUNT_ID = os.getenv("DERIV_ACCOUNT_ID", "DOT94309357")
DERIV_REST_BASE = "https://api.derivws.com/trading/v1/options"

# Trading Assets
SYMBOLS = {
    "R_75": {
        "name": "Volatility 75 Index",
        "symbol": "R_75",
        "min_stake": 0.35,  # Deriv minimum stake for synthetics ($)
        "default_stake": 1.0,
        "multiplier": 100,  # Multiplier leverage if trading Multipliers
    },
    "cryBTCUSD": {
        "name": "Bitcoin / USD",
        "symbol": "cryBTCUSD",
        "min_stake": 1.0,
        "default_stake": 2.0,
        "multiplier": 100,
    }
}

# Strategy Parameters (Bollinger Bands Mean Reversion)
TIMEFRAME_SECONDS = 900  # 15-Minute candles
BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
ATR_PERIOD = 14
STOP_LOSS_ATR_MULT = 1.5
TAKE_PROFIT_ATR_MULT = 2.5

# Risk Management
RISK_PER_TRADE_PCT = 0.015  # 1.5% of account equity
MAX_OPEN_PER_SYMBOL = 1
MAX_TOTAL_OPEN_TRADES = 2
MAX_DAILY_DRAWDOWN_PCT = 0.05  # Halt if account drops 5% in 24 hours
DEMO_MODE = True  # Safety check
