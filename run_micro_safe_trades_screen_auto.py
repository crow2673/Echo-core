from micro_safe_trading_bot_auto import MicroSafeTradingBotAuto
from screen_watcher_adapter import ScreenWatcherAdapter
from sandbox_adapter import SandboxAdapter

# Initialize bot
bot = MicroSafeTradingBotAuto(
    capital=20.0,
    min_buffer=2.0,
    max_fraction=0.5,
    profit_factor=0.05,
    fee_per_trade=0.2
)

# Screen region for platform (adjust manually)
screen_region = (0, 0, 800, 600)
screen_adapter = ScreenWatcherAdapter(region=screen_region, fee=0.2)

# Sandbox adapter for testing
sandbox_adapter = SandboxAdapter()

# Merge: first test sandbox
print("Running Sandbox Test...")
bot.run_platform_adapter_continuous(sandbox_adapter, interval=5)

# Then run live screen watching safely
print("Running Screen-Watched Trades...")
bot.run_platform_adapter_continuous(screen_adapter, interval=30)
