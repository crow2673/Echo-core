"""
EchoL1StrategyV6 — Long AND short. Profits in any market direction.

V4/V5 problem: long-only strategy loses in bear/sideways markets.
An AI should profit regardless of direction.

V6 adds short selling:
  Long:  RSI recovery from oversold + MACD turning up   + near MA50 + volume
  Short: RSI reversal from overbought + MACD turning down + near MA50 + volume

Exit: 5% TP | 2% SL (tighter — crypto moves fast both ways)
No trailing stop — let signals run to target.

Expected: long signals fire in dips, short signals fire at tops.
Net result: profits in bull, bear, AND sideways markets.
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta
import pandas as pd


class EchoL1StrategyV6(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"

    minimal_roi = {"0": 0.05}
    stoploss = -0.02
    trailing_stop = False
    can_short = True

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ma50"] = dataframe["close"].rolling(50).mean()
        dataframe["near_or_above_ma50"] = (
            dataframe["close"] > dataframe["ma50"] * 0.92
        ).astype(int)
        dataframe["near_or_below_ma50"] = (
            dataframe["close"] < dataframe["ma50"] * 1.08
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["vol_ma20"] = dataframe["volume"].rolling(20).mean()

        _macd, _signal, _hist = ta.MACD(dataframe["close"], fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd_hist"] = pd.Series(_hist, index=dataframe.index)
        dataframe["macd_hist_prev"] = dataframe["macd_hist"].shift(1)

        dataframe["rsi_prev"] = dataframe["rsi"].shift(1)

        # Long conditions
        dataframe["rsi_was_oversold"] = (dataframe["rsi_prev"] < 40).astype(int)
        dataframe["rsi_recovering"] = (
            (dataframe["rsi_was_oversold"] == 1) &
            (dataframe["rsi"] > dataframe["rsi_prev"])
        ).astype(int)
        dataframe["macd_turning_up"] = (
            dataframe["macd_hist"] > dataframe["macd_hist_prev"]
        ).astype(int)

        # Short conditions (mirror)
        dataframe["rsi_was_overbought"] = (dataframe["rsi_prev"] > 60).astype(int)
        dataframe["rsi_reversing"] = (
            (dataframe["rsi_was_overbought"] == 1) &
            (dataframe["rsi"] < dataframe["rsi_prev"])
        ).astype(int)
        dataframe["macd_turning_down"] = (
            dataframe["macd_hist"] < dataframe["macd_hist_prev"]
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long entry
        dataframe.loc[
            (dataframe["near_or_above_ma50_1d"] == 1) &
            (dataframe["rsi_recovering"] == 1) &
            (dataframe["rsi"] < 45) &
            (dataframe["macd_turning_up"] == 1) &
            (dataframe["volume"] > dataframe["vol_ma20"] * 1.2) &
            (dataframe["volume"] > 0),
            "enter_long",
        ] = 1

        # Short entry (mirror logic)
        dataframe.loc[
            (dataframe["near_or_below_ma50_1d"] == 1) &
            (dataframe["rsi_reversing"] == 1) &
            (dataframe["rsi"] > 55) &
            (dataframe["macd_turning_down"] == 1) &
            (dataframe["volume"] > dataframe["vol_ma20"] * 1.2) &
            (dataframe["volume"] > 0),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        dataframe.loc[:, "exit_short"] = 0
        return dataframe
