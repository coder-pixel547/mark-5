import logging
from typing import Dict, Any, Optional
import config

logger = logging.getLogger("OrderExecutor")

class OrderExecutor:
    def __init__(self, client, risk_manager):
        self.client = client
        self.risk_manager = risk_manager

    async def execute_trade(self, symbol: str, signal_data: Dict[str, Any]) -> bool:
        """Executes a BUY or SELL trade via Deriv Multiplier / CFD contract."""
        signal = signal_data["signal"]
        price = signal_data["price"]
        sl = signal_data["stop_loss"]
        tp = signal_data["take_profit"]

        # Check risk limits
        can_trade, reason = self.risk_manager.can_open_trade(symbol)
        if not can_trade:
            logger.warning(f"Trade blocked by Risk Manager: {reason}")
            return False

        # Calculate stake
        stake = self.risk_manager.calculate_stake(symbol, price, sl)
        sym_cfg = config.SYMBOLS.get(symbol, {})
        multiplier = sym_cfg.get("multiplier", 100)
        contract_type = "MULTUP" if signal == "BUY" else "MULTDOWN"

        # Calculate absolute SL and TP amount in USD
        sl_points = abs(price - sl)
        tp_points = abs(tp - price)
        sl_usd = round(stake * multiplier * (sl_points / price), 2)
        tp_usd = round(stake * multiplier * (tp_points / price), 2)

        logger.info(f"==> Placing {signal} on {symbol} | Stake: ${stake:.2f} | Mult: x{multiplier} | SL: -${sl_usd:.2f} | TP: +${tp_usd:.2f}")

        # Check if authorized for real/demo execution
        if self.client.is_authorized:
            try:
                # 1. Get contract proposal
                proposal_req = {
                    "proposal": 1,
                    "amount": stake,
                    "basis": "stake",
                    "contract_type": contract_type,
                    "currency": self.client.currency,
                    "symbol": symbol,
                    "multiplier": multiplier,
                    "limit_order": {
                        "stop_loss": sl_usd,
                        "take_profit": tp_usd
                    }
                }
                prop_res = await self.client.send_request(proposal_req)
                if "error" in prop_res:
                    logger.error(f"Proposal error: {prop_res['error'].get('message')}")
                    return False

                proposal_id = prop_res.get("proposal", {}).get("id")

                # 2. Buy contract
                buy_res = await self.client.send_request({
                    "buy": proposal_id,
                    "price": stake
                })
                if "error" in buy_res:
                    logger.error(f"Buy error: {buy_res['error'].get('message')}")
                    return False

                contract_id = buy_res.get("buy", {}).get("contract_id")
                logger.info(f"SUCCESS: Order executed on Deriv! Contract ID: {contract_id}")

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
                logger.error(f"Exception during order placement: {e}")
                return False
        else:
            # Paper trading / dry run simulation
            logger.info(f"[PAPER TRADING] Simulated {signal} order placed for {symbol} @ {price:.2f}")
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
            logger.info(f"<== Closing {pos_type} position on {symbol} @ {current_price:.2f} ({reason})")
            if self.client.is_authorized and pos.get("contract_id", "").isdigit():
                try:
                    await self.client.send_request({
                        "sell": pos["contract_id"],
                        "price": 0
                    })
                except Exception as e:
                    logger.error(f"Error closing contract on Deriv: {e}")
            self.risk_manager.close_position(symbol)
