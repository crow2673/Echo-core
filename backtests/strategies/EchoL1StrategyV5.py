"""
EchoL1StrategyV5 — Tighter exits to match actual signal quality.

V4 finding: true signal quality is ~27% chance of +8% before -3%.
At those odds, 0.92 profit factor — barely breakeven.

V5 fix: tighter stop loss (1.5% not 3%) + lower TP (5% not 8%).
Logic: these signals catch short recoveries, not sustained trends.
Cut losses faster. Take profits sooner.
Math: at 27% win rate → (0.27 × 5%) + (0.73 × -1.5%) = +0.26% per trade.
Breakeven win rate drops from 27.3% to 23.1%.

Entry: same as V3/V4 (RSI recovery + MACD + soft MA50 + volume spike)
Exit:  5% take profit | 1.5% stop loss | no trailing
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta


class EchoL1StrategyV5(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"

    minimal_roi = {"0": 0.05}
    stoploss = -0.015
    trailing_stop = False

    can_short = False

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ma50"] = dataframe["close"].rolling(50).mean()
        # Not a hard block — just a softened trend filter
        dataframe["near_or_above_ma50"] = (
            dataframe["close"] > dataframe["ma50"] * 0.92
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["ma10"] = dataframe["close"].rolling(10).mean()
        dataframe["vol_ma20"] = dataframe["volume"].rolling(20).mean()

        # MACD for momentum confirmation
        import pandas as pd
        _macd, _signal, _hist = ta.MACD(dataframe["close"], fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd_hist"] = pd.Series(_hist, index=dataframe.index)
        dataframe["macd_hist_prev"] = dataframe["macd_hist"].shift(1)
        dataframe["macd_turning"] = (
            (dataframe["macd_hist"] > dataframe["macd_hist_prev"]) &
            (dataframe["macd_hist"] > -50)
        ).astype(int)

        # RSI crossover: was below threshold, now recovering
        dataframe["rsi_prev"] = dataframe["rsi"].shift(1)
        dataframe["rsi_was_oversold"] = (dataframe["rsi_prev"] < 40).astype(int)
        dataframe["rsi_recovering"] = (
            (dataframe["rsi_was_oversold"] == 1) &
            (dataframe["rsi"] > dataframe["rsi_prev"])  # RSI rising
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            # Softened trend filter: within 8% of MA50 (not strictly above)
            (dataframe["near_or_above_ma50_1d"] == 1) &
            # RSI was oversold and is now rising
            (dataframe["rsi_recovering"] == 1) &
            # RSI still below 45 (fresh recovery, not already extended)
            (dataframe["rsi"] < 45) &
            # MACD momentum turning
            (dataframe["macd_turning"] == 1) &
            # Volume confirmation
            (dataframe["volume"] > dataframe["vol_ma20"] * 1.2) &
            (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        return dataframe
