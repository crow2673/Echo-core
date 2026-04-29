"""
EchoL1StrategyV2 — Improved L1 crypto strategy for Echo.

Changes from V1:
  1. Trend filter — only enter when price is above 200-period daily MA (bull market only)
  2. RSI crossover — buy recovery (RSI crosses UP through 35), not raw oversold
  3. Volume confirmation — entry bar volume must be above 20-bar average
  4. Wider take profit (8%) to let winners breathe vs tight 6%

Entry: Daily price > MA200 AND RSI crosses above 35 AND volume spike
Exit:  8% take profit | 3% stop loss | 2% trailing (activates at +3%)
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta


class EchoL1StrategyV2(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"

    minimal_roi = {"0": 0.08}          # 8% take profit — give winners room
    stoploss = -0.03                    # 3% stop loss (unchanged)
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    can_short = False

    # Pull in daily bars for trend filter
    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ma200"] = dataframe["close"].rolling(200).mean()
        dataframe["above_ma200"] = (dataframe["close"] > dataframe["ma200"]).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["ma10"] = dataframe["close"].rolling(10).mean()
        dataframe["vol_ma20"] = dataframe["volume"].rolling(20).mean()

        # RSI crossover: was below 35 last bar, now above 35 (recovery signal)
        dataframe["rsi_prev"] = dataframe["rsi"].shift(1)
        dataframe["rsi_cross_up"] = (
            (dataframe["rsi_prev"] < 35) &
            (dataframe["rsi"] >= 35)
        ).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            # Trend filter: daily close above 200-day MA
            (dataframe["above_ma200_1d"] == 1) &
            # RSI recovering from oversold (crossover, not just below)
            (dataframe["rsi_cross_up"] == 1) &
            # Price still above MA10 (short-term trend intact)
            (dataframe["close"] > dataframe["ma10"]) &
            # Volume spike — at least 1.2x average (confirmation)
            (dataframe["volume"] > dataframe["vol_ma20"] * 1.2) &
            (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        return dataframe
