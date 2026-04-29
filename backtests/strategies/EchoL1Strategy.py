"""
EchoL1Strategy — Freqtrade backtest mirror of Echo's crypto_brain.py L1 strategy.

Entry: RSI(14) < 35 AND price > MA10 on 1h bars (oversold + above trend)
Exit:  6% take profit | 3% stop loss | 2% trailing stop (activates at +3%)
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta


class EchoL1Strategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"

    # Match crypto_brain.py exactly
    minimal_roi = {"0": 0.06}          # 6% take profit
    stoploss = -0.03                    # 3% stop loss
    trailing_stop = True
    trailing_stop_positive = 0.02       # 2% trailing once in profit
    trailing_stop_positive_offset = 0.03  # activate trailing at +3%
    trailing_only_offset_is_reached = True

    # No leverage
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["ma10"] = dataframe["close"].rolling(10).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < 35) &
            (dataframe["close"] > dataframe["ma10"]) &
            (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ROI + trailing stop handle exits — no extra signal needed
        dataframe.loc[:, "exit_long"] = 0
        return dataframe
