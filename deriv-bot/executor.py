import logging
from typing import Dict, Any, Optional, Callable
import config

logger = logging.getLogger("OrderExecutor")

class OrderExecutor:
    def __init__(self, client, risk_manager, log_callback: Optional[Callable[[str], None]] = None):
        self.client = client
        self.risk_manager = risk_manager
        self.log = log_callback or (lambda msg: None)

    async def execute_trade(self, symbol: str, signal_data: Dict[str, Any]) -> bool:
        """Executes a BUY or SELL trade via Deriv Multiplier contract."""
        signal = signal_data["signal"]
        price = signal_data["price"]
        sl = signal_data["stop_loss"]
        tp = signal_data["take_profit"]

        # Check risk limits
        can_trade, reason = self.risk_manager.can_open_trade(symbol)
        if not can_trade:
            msg = f"Trade blocked by Risk Manager: {reason}"
            logger.warning(msg)
            self.log(f"<span style='color: orange;'>{msg}</span>")
            return False

        # Calculate stake
        stake = self.risk_manager.calculate_stake(symbol, price, sl)
        sym_cfg = config.SYMBOLS.get(symbol, {})
        multiplier = sym_cfg.get("multiplier", 100)
        contract_type = "MULTUP" if signal == "BUY" else "MULTDOWN"

        # Calculate SL and TP in USD (1:2 Risk/Reward)
        if getattr(config, "USE_FIXED_STAKE", False):
            sl_usd = float(getattr(config, "STOP_LOSS_USD", 0.80))
            tp_usd = float(getattr(config, "TAKE_PROFIT_USD", 1.60))
        else:
            sl_points = abs(price - sl)
            tp_points = abs(tp - price)
            sl_usd = round(stake * multiplier * (sl_points / price), 2)
            tp_usd = round(stake * multiplier * (tp_points / price), 2)
            if sl_usd >= stake:
                sl_usd = round(stake * 0.85, 2)
            if sl_usd < 0.10:
                sl_usd = 0.10
            if tp_usd < 0.10:
                tp_usd = round(stake * 1.5, 2)

        if tp_usd < 0.10:
            tp_usd = round(stake * 1.5, 2)

        info_msg = f"Placing {signal} on {symbol} | Stake: ${stake:.2f} | x{multiplier} | SL: -${sl_usd:.2f} | TP: +${tp_usd:.2f}"
        logger.info(info_msg)
        self.log(info_msg)

        # Check if authorized for execution
        if self.client.is_authorized:
            try:
                # 1. Get contract proposal (requires underlying_symbol for Multipliers)
                proposal_req = {
                    "proposal": 1,
                    "amount": round(stake, 2),
                    "basis": "stake",
                    "contract_type": contract_type,
                    "currency": self.client.currency,
                    "underlying_symbol": symbol,
                    "multiplier": multiplier,
                    "limit_order": {
                        "stop_loss": sl_usd,
                        "take_profit": tp_usd
                    }
                }
                prop_res = await self.client.send_request(proposal_req)
                if "error" in prop_res:
                    err_msg = prop_res["error"].get("message", "Unknown error")
                    logger.error(f"Proposal error: {err_msg}")
                    self.log(f"<span style='color: red;'>Proposal error: {err_msg}</span>")
                    return False

                proposal_id = prop_res.get("proposal", {}).get("id")

                # 2. Buy contract
                buy_res = await self.client.send_request({
                    "buy": proposal_id,
                    "price": round(stake, 2)
                })
                if "error" in buy_res:
                    err_msg = buy_res["error"].get("message", "Unknown error")
                    logger.error(f"Buy error: {err_msg}")
                    self.log(f"<span style='color: red;'>Buy error: {err_msg}</span>")
                    return False

                contract_id = buy_res.get("buy", {}).get("contract_id")
                success_msg = f"TRADE EXECUTED! Contract ID: {contract_id} | Type: {signal} {symbol} | Stake: ${stake:.2f}"
                logger.info(success_msg)
                self.log(f"<span style='color: #4ade80; font-weight: bold;'>{success_msg}</span>")

                self.risk_manager.register_position(symbol, {
                    "contract_id": contract_id,
                    "type": signal,
                    "entry_price": price,
                    "stake": stake,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "sma20": signal_data.get("sma20", price)
                })
                return True

            except Exception as e:
                err_msg = f"Exception during order placement: {e}"
                logger.error(err_msg)
                self.log(f"<span style='color: red;'>{err_msg}</span>")
                return False
        else:
            # Paper trading / dry run simulation
            sim_msg = f"[PAPER] Simulated {signal} order for {symbol} @ {price:.2f}"
            logger.info(sim_msg)
            self.log(sim_msg)
            self.risk_manager.register_position(symbol, {
                "contract_id": "SIM_PAPER_1",
                "type": signal,
                "entry_price": price,
                "stake": stake,
                "stop_loss": sl,
                "take_profit": tp,
                "sma20": signal_data.get("sma20", price)
            })
            return True

    async def check_exits(self, symbol: str, current_price: float):
        """Checks if open position should be closed at 20 SMA mean reversion or SL/TP."""
        pos = self.risk_manager.open_positions.get(symbol)
        if not pos:
            return

        pos_type = pos["type"]
        entry = pos["entry_price"]
        sl = pos["stop_loss"]
        tp = pos["take_profit"]
        sma20 = pos["sma20"]

        should_close = False
        reason = ""

        if pos_type == "BUY":
            if current_price <= sl:
                should_close = True
                reason = "Stop Loss Hit"
            elif current_price >= tp:
                should_close = True
                reason = "Take Profit Hit"
            elif current_price >= sma20:
                should_close = True
                reason = "Mean Reversion Target Reached (20 SMA)"

        elif pos_type == "SELL":
            if current_price >= sl:
                should_close = True
                reason = "Stop Loss Hit"
            elif current_price <= tp:
                should_close = True
                reason = "Take Profit Hit"
            elif current_price <= sma20:
                should_close = True
                reason = "Mean Reversion Target Reached (20 SMA)"

        if should_close:
            close_msg = f"Closing {pos_type} on {symbol} @ {current_price:.2f} ({reason})"
            logger.info(close_msg)
            self.log(f"<span style='color: #facc15;'>{close_msg}</span>")
            contract_id = pos.get("contract_id")
            if self.client.is_authorized and contract_id and str(contract_id).isdigit():
                try:
                    await self.client.send_request({
                        "sell": contract_id,
                        "price": 0
                    })
                except Exception as e:
                    logger.error(f"Error closing contract on Deriv: {e}")
            self.risk_manager.close_position(symbol)
