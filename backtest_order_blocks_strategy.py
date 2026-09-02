import argparse
import os
from datetime import datetime

import numpy as np
import pandas as pd


PIP = 0.0001
INITIAL_CAPITAL = 10_000.0
RISK_PER_TRADE = 0.01
RISK_REWARD = 2.0
FIBONACCI_RETRACEMENT = 0.62
WINDOW = 20
SWEEP_LOOKBACK = 6
BODY_MIN_PIPS = 2.0
BREAK_MIN_PIPS = 2.0
FVG_MIN_PIPS = 0.5
SPREAD_POINTS_TO_PRICE = 0.00001
EUROPEAN_SESSION = ((7, 0), (10, 0))
AMERICAN_SESSION = ((14, 30), (17, 0))


OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(
    OUTPUT_DIR, "EURUSD_M1_202605270610_202609011829.csv"
)


def load_mt5_csv(csv_path):
    df = pd.read_csv(csv_path, sep="\t")
    df.columns = [column.strip("<>").lower() for column in df.columns]
    df["time"] = pd.to_datetime(
        df["date"] + " " + df["time"],
        format="%Y.%m.%d %H:%M:%S",
    )
    df = df.drop(columns=["date"])
    required = {"time", "open", "high", "low", "close", "spread"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans le CSV : {sorted(missing)}")
    if not df["time"].is_monotonic_increasing:
        df = df.sort_values("time").reset_index(drop=True)
    return df


def _minutes_of_day(timestamp):
    return timestamp.hour * 60 + timestamp.minute


def _in_session(timestamp, session):
    start, end = session
    minutes = _minutes_of_day(timestamp)
    start_minutes = start[0] * 60 + start[1]
    end_minutes = end[0] * 60 + end[1]
    return start_minutes <= minutes <= end_minutes


def detect_order_blocks(df, min_stars=3):
    """Détecte les OB sans utiliser de bougies postérieures à leur confirmation."""
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    times = df["time"].to_numpy()
    n = len(df)
    order_blocks = []

    for index in range(SWEEP_LOOKBACK, n - 2):
        bullish = closes[index] < opens[index] and closes[index + 1] > opens[index + 1] and closes[index + 2] > opens[index + 2]
        bearish = closes[index] > opens[index] and closes[index + 1] < opens[index + 1] and closes[index + 2] < opens[index + 2]
        if not bullish and not bearish:
            continue

        ob_type = "BULLISH" if bullish else "BEARISH"
        impulse_body_pips = abs(closes[index + 1] - opens[index + 1]) / PIP
        if impulse_body_pips < BODY_MIN_PIPS:
            continue

        break_pips = (
            (closes[index + 2] - highs[index]) / PIP
            if bullish
            else (lows[index] - closes[index + 2]) / PIP
        )
        if break_pips < BREAK_MIN_PIPS:
            continue

        zone_low = min(opens[index], closes[index])
        zone_high = max(opens[index], closes[index])
        structure_start = max(0, index - WINDOW)
        prior_lows = lows[structure_start:index]
        prior_highs = highs[structure_start:index]
        if bullish:
            extreme = lows[index] <= prior_lows.min()
            sweep = lows[index] < lows[index - SWEEP_LOOKBACK:index].min()
            fvg_size = (lows[index + 2] - highs[index]) / PIP
        else:
            extreme = highs[index] >= prior_highs.max()
            sweep = highs[index] > highs[index - SWEEP_LOOKBACK:index].max()
            fvg_size = (lows[index] - highs[index + 2]) / PIP

        ob_time = pd.Timestamp(times[index])
        session = _in_session(ob_time, EUROPEAN_SESSION) or _in_session(ob_time, AMERICAN_SESSION)
        fvg = fvg_size >= FVG_MIN_PIPS
        impulse_high = max(highs[index + 1], highs[index + 2])
        impulse_low = min(lows[index + 1], lows[index + 2])
        impulse_range = impulse_high - impulse_low
        fibonacci_level = (
            impulse_high - FIBONACCI_RETRACEMENT * impulse_range
            if bullish
            else impulse_low + FIBONACCI_RETRACEMENT * impulse_range
        )
        criteria = {
            "fvg": bool(fvg),
            "sweep": bool(sweep),
            "extreme": bool(extreme),
            "unmitigated": True,
            "volatility_session": bool(session),
        }
        stars = sum(criteria.values())
        if stars < min_stars:
            continue

        order_blocks.append({
            "type": ob_type,
            "index": index,
            "confirm_index": index + 2,
            "ob_time": ob_time,
            "confirm_time": pd.Timestamp(times[index + 2]),
            "zone_low": zone_low,
            "zone_high": zone_high,
            "fibonacci_level": fibonacci_level,
            "stars": stars,
            "criteria": criteria,
        })

    return order_blocks


def is_reaction_candle(df, index, trade_type, fibonacci_level):
    if index == 0:
        return False
    candle = df.iloc[index]
    previous = df.iloc[index - 1]
    body = abs(candle["close"] - candle["open"])
    if body == 0:
        return False

    if trade_type == "BUY":
        engulfing = (
            candle["close"] > candle["open"]
            and previous["close"] < previous["open"]
            and candle["open"] <= previous["close"]
            and candle["close"] >= previous["open"]
        )
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        hammer = candle["close"] > candle["open"] and lower_wick >= 2 * body
        fib_retest = candle["low"] <= fibonacci_level <= candle["close"]
    else:
        engulfing = (
            candle["close"] < candle["open"]
            and previous["close"] > previous["open"]
            and candle["open"] >= previous["close"]
            and candle["close"] <= previous["open"]
        )
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        pin_bar = candle["close"] < candle["open"] and upper_wick >= 2 * body
        fib_retest = candle["close"] <= fibonacci_level <= candle["high"]
        hammer = pin_bar

    return (engulfing or hammer) and fib_retest


def _touches_zone(row, order_block):
    return row["low"] <= order_block["zone_high"] and row["high"] >= order_block["zone_low"]


def run_backtest(df, order_blocks, initial_capital=INITIAL_CAPITAL):
    capital = initial_capital
    trades = []
    equity_curve = []
    used_ob_indices = set()
    pending = None
    active = None

    for index in range(WINDOW, len(df)):
        row = df.iloc[index]

        if pending is not None and active is None:
            entry_adjustment = pending["spread"] / 2 if pending["type"] == "BUY" else -pending["spread"] / 2
            entry = row["open"] + entry_adjustment
            if (pending["type"] == "BUY" and entry <= pending["sl"]) or (pending["type"] == "SELL" and entry >= pending["sl"]):
                pending = None
            else:
                risk_distance = abs(entry - pending["sl"])
                tp = entry + risk_distance * RISK_REWARD if pending["type"] == "BUY" else entry - risk_distance * RISK_REWARD
                risk_per_unit = (risk_distance + 2 * pending["slippage"]) * pending["point_value"]
                position_size = capital * RISK_PER_TRADE / risk_per_unit if risk_per_unit > 0 else 0.0
                active = {
                    **pending,
                    "entry": entry,
                    "entry_time": row["time"],
                    "tp": tp,
                    "initial_sl": pending["sl"],
                    "position_size": position_size,
                    "risk_distance": risk_distance,
                    "be_triggered": False,
                }
                pending = None

        if active is None:
            candidates = []
            for order_block in order_blocks:
                if order_block["index"] in used_ob_indices or order_block["confirm_index"] >= index:
                    continue
                if not _touches_zone(row, order_block):
                    continue
                if is_reaction_candle(df, index, "BUY" if order_block["type"] == "BULLISH" else "SELL", order_block["fibonacci_level"]):
                    prior_touches = any(
                        _touches_zone(df.iloc[prior_index], order_block)
                        for prior_index in range(order_block["confirm_index"] + 1, index)
                    )
                    if not prior_touches:
                        candidates.append(order_block)
            if candidates:
                order_block = max(candidates, key=lambda item: item["index"])
                used_ob_indices.add(order_block["index"])
                spread = float(row["spread"]) * SPREAD_POINTS_TO_PRICE
                pending = {
                    "type": "BUY" if order_block["type"] == "BULLISH" else "SELL",
                    "sl": order_block["zone_low"] if order_block["type"] == "BULLISH" else order_block["zone_high"],
                    "bos": order_block["zone_high"] if order_block["type"] == "BULLISH" else order_block["zone_low"],
                    "signal_time": row["time"],
                    "signal_index": index,
                    "order_block_index": order_block["index"],
                    "stars": order_block["stars"],
                    "fibonacci_level": order_block["fibonacci_level"],
                    "spread": spread,
                    "slippage": 0.0,
                    "point_value": 1.0,
                }

        if active is not None:
            if active["type"] == "BUY":
                stop_hit = row["low"] <= active["sl"]
                target_hit = row["high"] >= active["tp"]
                trigger = active["entry"] + active["risk_distance"]
                if not active["be_triggered"] and row["high"] >= trigger and not stop_hit:
                    active["sl"] = active["entry"]
                    active["be_triggered"] = True
                if stop_hit:
                    exit_price = active["sl"] - active["spread"] / 2
                    result = "BE" if active["be_triggered"] else "LOSS"
                elif target_hit:
                    exit_price = active["tp"] - active["spread"] / 2
                    result = "WIN"
                else:
                    equity_curve.append(capital)
                    continue
                profit = (exit_price - active["entry"]) * active["position_size"] - active["commission"] if "commission" in active else (exit_price - active["entry"]) * active["position_size"]
            else:
                stop_hit = row["high"] >= active["sl"]
                target_hit = row["low"] <= active["tp"]
                trigger = active["entry"] - active["risk_distance"]
                if not active["be_triggered"] and row["low"] <= trigger and not stop_hit:
                    active["sl"] = active["entry"]
                    active["be_triggered"] = True
                if stop_hit:
                    exit_price = active["sl"] + active["spread"] / 2
                    result = "BE" if active["be_triggered"] else "LOSS"
                elif target_hit:
                    exit_price = active["tp"] + active["spread"] / 2
                    result = "WIN"
                else:
                    equity_curve.append(capital)
                    continue
                profit = (active["entry"] - exit_price) * active["position_size"]

            capital += profit
            trades.append({**active, "exit_price": exit_price, "exit_time": row["time"], "result": result, "profit": profit})
            active = None

        equity_curve.append(capital)

    if active is not None:
        last_row = df.iloc[-1]
        if active["type"] == "BUY":
            exit_price = last_row["close"] - active["spread"] / 2
            profit = (exit_price - active["entry"]) * active["position_size"]
        else:
            exit_price = last_row["close"] + active["spread"] / 2
            profit = (active["entry"] - exit_price) * active["position_size"]
        capital += profit
        trades.append({**active, "exit_price": exit_price, "exit_time": last_row["time"], "result": "END", "profit": profit})

    df = df.copy()
    df["capital"] = initial_capital
    df.loc[df.index[WINDOW:WINDOW + len(equity_curve)], "capital"] = equity_curve
    if len(equity_curve) < len(df) - WINDOW:
        df.loc[df.index[WINDOW + len(equity_curve):], "capital"] = capital
    return trades, df, capital


def make_stats(df, trades, initial_capital):
    wins = [trade["profit"] for trade in trades if trade["result"] == "WIN"]
    losses = [trade["profit"] for trade in trades if trade["result"] == "LOSS"]
    bes = [trade["profit"] for trade in trades if trade["result"] == "BE"]
    ends = [trade["profit"] for trade in trades if trade["result"] == "END"]
    total = len(trades)
    equity = df["capital"].to_numpy()
    running_max = np.maximum.accumulate(equity)
    drawdowns = np.divide(equity - running_max, running_max, out=np.zeros_like(equity), where=running_max != 0) * 100
    return {
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "bes": len(bes),
        "ends": len(ends),
        "win_rate": len(wins) / total * 100 if total else 0.0,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else float("inf"),
        "expectancy": sum(trade["profit"] for trade in trades) / total if total else 0.0,
        "final_capital": initial_capital + sum(trade["profit"] for trade in trades),
        "net_profit": sum(trade["profit"] for trade in trades),
        "max_drawdown": float(drawdowns.min()) if len(drawdowns) else 0.0,
    }


def compute_hourly_volatility(df):
    """Calcule la répartition de l'amplitude moyenne des bougies par heure."""
    hourly = df.assign(
        hour=df["time"].dt.hour,
        range_pips=(df["high"] - df["low"]) / PIP,
    ).groupby("hour")["range_pips"].agg(["count", "mean", "median", "sum"])
    total_range = hourly["sum"].sum()
    profile = []
    for hour in range(24):
        if hour in hourly.index:
            values = hourly.loc[hour]
            profile.append({
                "hour": hour,
                "candles": int(values["count"]),
                "average_pips": float(values["mean"]),
                "median_pips": float(values["median"]),
                "range_share": float(values["sum"] / total_range * 100) if total_range else 0.0,
            })
        else:
            profile.append({
                "hour": hour,
                "candles": 0,
                "average_pips": 0.0,
                "median_pips": 0.0,
                "range_share": 0.0,
            })
    return profile


def write_log(csv_path, order_blocks, trades, stats, min_stars, log_path, hourly_volatility):
    lines = [
        "=== BILAN FINANCIER - STRATEGIE ORDER BLOCKS ===",
        f"Date d'exécution : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"CSV source : {os.path.abspath(csv_path)}",
        f"Capital initial : {INITIAL_CAPITAL:.2f} EUR",
        f"Paramètres : min_stars={min_stars}, risque={RISK_PER_TRADE:.2%}, RR={RISK_REWARD:.2f}, Fibonacci={FIBONACCI_RETRACEMENT:.2f}",
        f"Order Blocks retenus : {len(order_blocks)}",
        "",
        "--- TRADES OUVERTS ET CLOTURES ---",
    ]
    for number, trade in enumerate(trades, start=1):
        lines.append(
            f"#{number:03d} {trade['type']} | OB={trade['order_block_index']} | étoiles={trade['stars']} "
            f"| signal={trade['signal_time']} | entrée={trade['entry_time']} @ {trade['entry']:.5f} "
            f"| SL initial={trade['initial_sl']:.5f} | TP={trade['tp']:.5f} "
            f"| sortie={trade['exit_time']} @ {trade['exit_price']:.5f} "
            f"| résultat={trade['result']} | P&L={trade['profit']:+.2f} EUR"
        )
    if not trades:
        lines.append("Aucun trade exécuté.")
    lines.extend([
        "",
        "--- REPARTITION DE LA VOLATILITE SUR 24H ---",
        "Heure | Bougies | Amplitude moyenne (pips) | Médiane (pips) | Part de l'amplitude totale",
    ])
    for values in hourly_volatility:
        lines.append(
            f"{values['hour']:02d}h | {values['candles']:7d} | {values['average_pips']:23.3f} "
            f"| {values['median_pips']:15.3f} | {values['range_share']:25.2f}%"
        )
    lines.extend([
        "",
        "--- RESULTAT FINAL UNIQUE ---",
        f"Trades clôturés : {stats['total']}",
        f"WIN / LOSS / BE / END : {stats['wins']} / {stats['losses']} / {stats['bes']} / {stats['ends']}",
        f"Win rate : {stats['win_rate']:.2f}%",
        f"Profit factor : {stats['profit_factor']:.4f}",
        f"Espérance par trade : {stats['expectancy']:+.2f} EUR",
        f"Capital final : {stats['final_capital']:.2f} EUR",
        f"Profit net : {stats['net_profit']:+.2f} EUR",
        f"Drawdown maximum : {stats['max_drawdown']:.2f}%",
    ])
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Backtest Order Blocks sur le CSV EUR/USD M1 du projet.")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Chemin du CSV MT5")
    parser.add_argument("--min-stars", type=int, default=3, choices=range(0, 6))
    parser.add_argument("--log", default=None, help="Chemin du journal de sortie")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        raise FileNotFoundError(f"CSV introuvable : {args.csv}")
    df = load_mt5_csv(args.csv)
    order_blocks = detect_order_blocks(df, min_stars=args.min_stars)
    trades, result_df, final_capital = run_backtest(df, order_blocks)
    stats = make_stats(result_df, trades, INITIAL_CAPITAL)
    hourly_volatility = compute_hourly_volatility(df)
    log_path = args.log or os.path.join(
        OUTPUT_DIR, f"backtest_order_blocks_{datetime.now():%Y%m%d_%H%M%S}.log"
    )
    write_log(args.csv, order_blocks, trades, stats, args.min_stars, log_path, hourly_volatility)

    print("=== RESULTAT FINAL UNIQUE ===")
    print(f"CSV source          : {os.path.abspath(args.csv)}")
    print(f"Capital initial     : {INITIAL_CAPITAL:.2f} EUR")
    print(f"Order Blocks retenus: {len(order_blocks)}")
    print(f"Trades clôturés     : {stats['total']}")
    print(f"WIN / LOSS / BE / END : {stats['wins']} / {stats['losses']} / {stats['bes']} / {stats['ends']}")
    print(f"Capital final       : {final_capital:.2f} EUR")
    print(f"Profit net          : {stats['net_profit']:+.2f} EUR")
    print(f"Drawdown maximum    : {stats['max_drawdown']:.2f}%")
    print(f"Journal             : {os.path.abspath(log_path)}")


if __name__ == "__main__":
    main()
