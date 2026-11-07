import logging
from typing import Dict, Any, Tuple, Optional
import config

logger = logging.getLogger("RiskManager")

class RiskManager:
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.daily_start_balance = initial_balance
        self.daily_pnl = 0.0

    def update_balance(self, balance: float):
        self.current_balance = balance

    def can_open_trade(self, symbol: str) -> Tuple[bool, str]:
        """Validates whether a new trade can be opened under risk rules."""
        # 1. Check max daily drawdown limit
        daily_loss = self.daily_start_balance - self.current_balance
        if daily_loss >= self.daily_start_balance * config.MAX_DAILY_DRAWDOWN_PCT:
            return False, f"Daily drawdown limit reached (-{config.MAX_DAILY_DRAWDOWN_PCT*100}%). Trading paused."

        # 2. Check total open positions cap
        if len(self.open_positions) >= config.MAX_TOTAL_OPEN_TRADES:
            return False, f"Max total open positions reached ({config.MAX_TOTAL_OPEN_TRADES})."

        # 3. Check position on this specific symbol
        if symbol in self.open_positions:
            return False, f"A position is already open for {symbol}."

        return True, "Risk check passed."

    def calculate_stake(self, symbol: str, entry_price: float, stop_loss: float) -> float:
        """
        Calculates position stake. If USE_FIXED_STAKE is enabled, returns fixed stake ($1.00).
        Otherwise dynamically scales based on 1.5% account equity risk.
        """
        if getattr(config, "USE_FIXED_STAKE", False):
            return float(getattr(config, "FIXED_STAKE_USD", 1.00))

        sym_cfg = config.SYMBOLS.get(symbol, {})
        min_stake = sym_cfg.get("min_stake", 0.35)
        
        # Risk 1.5% of current equity
        risk_budget = self.current_balance * config.RISK_PER_TRADE_PCT
        
        # Stop loss percentage distance
        sl_distance_pct = abs(entry_price - stop_loss) / (entry_price + 1e-9)
        
        # If trading Multipliers or CFDs
        multiplier = sym_cfg.get("multiplier", 100)
        
        # Stake * Multiplier * sl_distance_pct = risk_budget
        if sl_distance_pct > 0 and multiplier > 0:
            raw_stake = risk_budget / (multiplier * sl_distance_pct)
        else:
            raw_stake = risk_budget * 0.1
            
        final_stake = max(raw_stake, min_stake)
        # Cap stake at 5% of balance for absolute safety
        final_stake = min(final_stake, self.current_balance * 0.05)
        
        return round(final_stake, 2)

    def register_position(self, symbol: str, pos_data: Dict[str, Any]):
        self.open_positions[symbol] = pos_data
        logger.info(f"Position opened on {symbol}: {pos_data['type']} @ {pos_data['entry_price']}")

    def close_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        pos = self.open_positions.pop(symbol, None)
        if pos:
            logger.info(f"Position closed on {symbol}")
        return pos
