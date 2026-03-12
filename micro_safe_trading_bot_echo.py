from micro_safe_trading_bot_multi_platform import MicroSafeTradingBotMultiPlatform

class MicroSafeTradingBotEcho(MicroSafeTradingBotMultiPlatform):
    def run_echo_ai_feed(self, echo_feed_generator):
        """
        echo_feed_generator: generator that yields trade suggestions
        Each element: (principal, monthly_rate, months, fee)
        """
        results = []
        for trade in echo_feed_generator:
            principal, rate, months, fee = trade
            approved = self.evaluate_trade_with_fee(principal, rate, months, fee)
            results.append({
                "trade": trade,
                "approved": approved,
                "capital_after": self.capital
            })
            print(f"Trade {trade} -> {'APPROVED ✅' if approved else 'REJECTED ❌'} | Capital: ${self.capital:.2f}")
        return results
