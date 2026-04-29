"""
EchoL1StrategyV3 — Further refined L1 strategy.

V2 problem: MA200 filter blocked everything (market spent most of year below it).

V3 changes:
  1. Trend filter: 50-day MA (more responsive) instead of 200-day
  2. Softer filter: allow entries when price is within 8% below MA50
     (markets recover from below MA50, not just above it)
  3. RSI threshold raised to < 40 for oversold (catches more recoveries)
  4. RSI crossover above 35 as confirmation of actual recovery
  5. Added MACD signal confirmation (momentum turning positive)
  6. Keep volume spike requirement

Entry: (close > MA50 OR close > MA50 * 0.92) AND RSI cross up 35 AND MACD hist turning + AND volume spike
Exit:  8% take profit | 3% stop | 2% trailing at +3%
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta


class EchoL1StrategyV3(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"

    minimal_roi = {"0": 0.08}
    stoploss = -0.03
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

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
