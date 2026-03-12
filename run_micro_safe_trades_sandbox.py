from micro_safe_trading_bot_live import MicroSafeTradingBotLive
from sandbox_adapter import SandboxAdapter

# Initialize bot
bot = MicroSafeTradingBotLive(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.2
)

# Connect to sandbox
sandbox = SandboxAdapter()

print("Starting Sandbox MicroSafe Trading Bot...")

# Get trades and run through bot
trades = sandbox.get_trades()
results = bot.run_platform_adapter(sandbox)

for r in results:
    t = r["trade"]
    print(f"Trade {t} -> {'APPROVED ✅' if r['approved'] else 'REJECTED ❌'} | Current Capital: ${bot.capital:.2f}")

print(f"Final Capital after sandbox: ${bot.capital:.2f}")
