"""Backtest causal du Model A de la specification Order Block v2.1."""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PIP = 0.0001
DEFAULT_CSV = Path(__file__).with_name("EURUSD_M1_202605270610_202609011829.csv")


@dataclass
class Parameters:
    atr_period: int = 20
    atr_multiplier: float = 1.5
    atr_base_pips: float = 10.0
    max_candles: int = 20
    bos_lookback: int = 50
    bos_mode: str = "directional"
    use_fvg: bool = False
    use_swing: bool = False
    use_extremum: bool = False
    use_trading_window: bool = False
    fvg_atr_multiplier: float = 1.0
    fvg_min_pips: float = 5.0
    extremum_lookback: int = 20
    trading_start_hour: int = 8
    trading_end_hour: int = 22
    buffer_multiplier: float = 1.0
    buffer_min_pips: float = 3.0
    reaction_atr_multiplier: float = 0.5
    reaction_min_pips: float = 0.5
    reaction_window: int = 3
    rr: float = 2.0
    be_at_r: float = 1.0
    capital: float = 10_000.0
    risk_pct: float = 0.01
    spread_pips: float = 1.2
    commission_pips: float = 1.0
    slippage_pips: float = 1.0
    block_expiry: int = 500


@dataclass
class ModelAOrderBlock:
    identifier: int
    created_index: int
    direction: str
    zone_low: float
    zone_high: float
    atr: float
    eligible: bool
    state: str = "ACTIVE"
    touch_index: int | None = None


@dataclass
class ModelAPosition:
    block_id: int
    direction: str
    signal_index: int
    entry_index: int
    entry_time: pd.Timestamp
    entry: float
    initial_sl: float
    sl: float
    tp: float
    lots: float
    risk_pips: float
    break_even: bool = False


def load_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path, sep="\t")
    data.columns = [column.strip("<>").lower() for column in data.columns]
    required = {"date", "time", "open", "high", "low", "close"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes : {sorted(missing)}")

    data["time"] = pd.to_datetime(
        data["date"] + " " + data["time"], format="%Y.%m.%d %H:%M:%S"
    )
    data = data.sort_values("time").reset_index(drop=True)
    for column in ("open", "high", "low", "close"):
        data[column] = pd.to_numeric(data[column], errors="raise")
    return data


def add_atr(data: pd.DataFrame, period: int) -> pd.DataFrame:
    result = data.copy()
    previous_close = result["close"].shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr"] = true_range.rolling(period, min_periods=period).mean()
    return result


class Strategy:
    def __init__(self, data: pd.DataFrame, parameters: Parameters):
        self.data = data
        self.parameters = parameters
        self.times = data["time"].to_numpy()
        self.opens = data["open"].to_numpy()
        self.highs = data["high"].to_numpy()
        self.lows = data["low"].to_numpy()
        self.closes = data["close"].to_numpy()
        self.atrs = data["atr"].to_numpy()
        self.blocks: list[ModelAOrderBlock] = []
        self.active_blocks: list[ModelAOrderBlock] = []
        self.pending: tuple[ModelAOrderBlock, int] | None = None
        self.position: ModelAPosition | None = None
        self.trades: list[dict] = []
        self.equity: list[float] = []
        self.capital = parameters.capital
        self.impulses_detected = 0
        self.blocks_touched = 0
        self.reaction_rejections = 0
        self.entry_rejections = 0
        self.signals_confirmed = 0
        self.filter_rejections = 0

    def detect_impulse(self, index: int) -> tuple[str, int] | None:
        params = self.parameters
        if index < params.atr_period + params.max_candles + params.bos_lookback + 1:
            return None
        atr = self.atrs[index]
        if pd.isna(atr):
            return None

        start = index - params.max_candles
        low_index = start + int(np.argmin(self.lows[start:index + 1]))
        high_index = start + int(np.argmax(self.highs[start:index + 1]))
        min_amplitude = max(params.atr_multiplier * atr, params.atr_base_pips * PIP)

        upward_amplitude = self.closes[index] - self.lows[low_index]
        prior_lows = self.lows[low_index - params.bos_lookback:low_index]
        prior_highs = self.highs[low_index - params.bos_lookback:low_index]
        upward_bos = (
            self.closes[index] > prior_highs.max()
            if params.bos_mode == "directional"
            else self.lows[index] < prior_lows.min() < self.closes[index]
        )
        if upward_amplitude >= min_amplitude and upward_bos:
            return "long", low_index

        downward_amplitude = self.highs[high_index] - self.closes[index]
        prior_lows = self.lows[high_index - params.bos_lookback:high_index]
        prior_highs = self.highs[high_index - params.bos_lookback:high_index]
        downward_bos = (
            self.closes[index] < prior_lows.min()
            if params.bos_mode == "directional"
            else self.highs[index] > prior_highs.max() > self.closes[index]
        )
        if downward_amplitude >= min_amplitude and downward_bos:
            return "short", high_index
        return None

    def create_block(self, index: int, direction: str, impulse_start: int) -> None:
        source_index = impulse_start - 1
        if source_index < 0:
            return
        block = ModelAOrderBlock(
            identifier=len(self.blocks) + 1,
            created_index=index,
            direction=direction,
            zone_low=self.lows[source_index],
            zone_high=self.highs[source_index],
            atr=self.atrs[index],
            eligible=self._filters_pass(index, source_index, direction),
        )
        self.blocks.append(block)
        self.active_blocks.append(block)
        self.impulses_detected += 1

    def _filters_pass(self, index: int, source_index: int, direction: str) -> bool:
        params = self.parameters
        if params.use_fvg:
            gap = (
                self.lows[index] - self.highs[index - 2]
                if direction == "long"
                else self.lows[index - 2] - self.highs[index]
            )
            min_gap = max(params.fvg_atr_multiplier * self.atrs[index], params.fvg_min_pips * PIP)
            if gap < min_gap:
                return False
        if params.use_swing:
            if source_index < 2 or source_index + 2 > index:
                return False
            if direction == "long":
                if not self.lows[source_index] < min(self.lows[source_index - 2:source_index]):
                    return False
                if not self.lows[source_index] < min(self.lows[source_index + 1:source_index + 3]):
                    return False
            else:
                if not self.highs[source_index] > max(self.highs[source_index - 2:source_index]):
                    return False
                if not self.highs[source_index] > max(self.highs[source_index + 1:source_index + 3]):
                    return False
        if params.use_extremum:
            start = max(0, source_index - params.extremum_lookback)
            values = self.lows[start:source_index + 1] if direction == "long" else self.highs[start:source_index + 1]
            source_value = self.lows[source_index] if direction == "long" else self.highs[source_index]
            if source_value != (values.min() if direction == "long" else values.max()):
                return False
        if params.use_trading_window:
            timestamp = pd.Timestamp(self.times[index])
            if timestamp.dayofweek >= 5 or not params.trading_start_hour <= timestamp.hour <= params.trading_end_hour:
                return False
        return True

    def _reaction_ok(self, block: ModelAOrderBlock, index: int) -> bool:
        clearance = max(
            self.parameters.reaction_atr_multiplier * block.atr,
            self.parameters.reaction_min_pips * PIP,
        )
        if block.direction == "long":
            return self.closes[index] > self.opens[index] and self.closes[index] > block.zone_high + clearance
        return self.closes[index] < self.opens[index] and self.closes[index] < block.zone_low - clearance

    def _position_size(self, entry: float, sl: float) -> tuple[float, float]:
        params = self.parameters
        risk_pips = abs(entry - sl) / PIP
        all_costs_pips = params.spread_pips + params.commission_pips + params.slippage_pips
        lots = (self.capital * params.risk_pct) / ((risk_pips + all_costs_pips) * 10.0)
        return np.floor(lots * 100.0) / 100.0, risk_pips

    def open_pending_position(self, index: int) -> None:
        if self.pending is None or self.position is not None:
            return
        block, signal_index = self.pending
        params = self.parameters
        entry_adjustment = (params.spread_pips / 2.0 + params.slippage_pips / 2.0) * PIP
        raw_open = self.opens[index]
        entry = raw_open + entry_adjustment if block.direction == "long" else raw_open - entry_adjustment
        buffer = max(params.buffer_multiplier * block.atr, params.buffer_min_pips * PIP)
        sl = block.zone_low - buffer if block.direction == "long" else block.zone_high + buffer
        valid = entry > sl if block.direction == "long" else entry < sl
        if valid:
            lots, risk_pips = self._position_size(entry, sl)
            if lots >= 0.01:
                distance = abs(entry - sl)
                tp = entry + params.rr * distance if block.direction == "long" else entry - params.rr * distance
                self.position = ModelAPosition(
                    block_id=block.identifier,
                    direction=block.direction,
                    signal_index=signal_index,
                    entry_index=index,
                    entry_time=self.times[index],
                    entry=entry,
                    initial_sl=sl,
                    sl=sl,
                    tp=tp,
                    lots=lots,
                    risk_pips=risk_pips,
                )
                block.state = "CONFIRMED"
            else:
                block.state = "REJECTED"
                self.entry_rejections += 1
        else:
            block.state = "REJECTED"
            self.entry_rejections += 1
        self.pending = None

    def close_position(self, index: int, raw_exit: float, reason: str) -> None:
        assert self.position is not None
        position = self.position
        params = self.parameters
        exit_adjustment = (params.spread_pips / 2.0 + params.slippage_pips / 2.0) * PIP
        exit_price = raw_exit - exit_adjustment if position.direction == "long" else raw_exit + exit_adjustment
        direction = 1.0 if position.direction == "long" else -1.0
        gross_pips = direction * (exit_price - position.entry) / PIP
        net_pips = gross_pips - params.commission_pips
        pnl_usd = net_pips * position.lots * 10.0
        self.capital += pnl_usd
        self.trades.append(
            {
                "block_id": position.block_id,
                "entry_index": position.entry_index,
                "direction": position.direction,
                "signal_time": self.times[position.signal_index],
                "entry_time": position.entry_time,
                "exit_time": self.times[index],
                "entry": position.entry,
                "initial_sl": position.initial_sl,
                "tp": position.tp,
                "exit": exit_price,
                "lots": position.lots,
                "risk_pips": position.risk_pips,
                "gross_pips": gross_pips,
                "net_pips": net_pips,
                "pnl_usd": pnl_usd,
                "reason": reason,
                "capital_after": self.capital,
            }
        )
        self.blocks[position.block_id - 1].state = "CLOSED"
        self.position = None

    def manage_position(self, index: int) -> None:
        if self.position is None:
            return
        position = self.position
        if position.direction == "long":
            sl_hit = self.lows[index] <= position.sl
            tp_hit = self.highs[index] >= position.tp
        else:
            sl_hit = self.highs[index] >= position.sl
            tp_hit = self.lows[index] <= position.tp

        # L'ordre intrabougie est inconnu en M1 : le stop prévaut dans le doute.
        if sl_hit:
            self.close_position(index, position.sl, "BE" if position.break_even else "SL")
        elif tp_hit:
            self.close_position(index, position.tp, "TP")
        elif not position.break_even:
            trigger = position.entry + self.parameters.be_at_r * (position.entry - position.initial_sl)
            reached = self.highs[index] >= trigger if position.direction == "long" else self.lows[index] <= trigger
            if reached:
                position.sl = position.entry
                position.break_even = True

    def update_blocks(self, index: int) -> None:
        remaining_blocks = []
        for block in self.active_blocks:
            if block.state == "ACTIVE":
                if index - block.created_index > self.parameters.block_expiry:
                    block.state = "EXPIRED"
                elif not block.eligible:
                    block.state = "REJECTED"
                    self.filter_rejections += 1
                elif self.lows[index] <= block.zone_high and self.highs[index] >= block.zone_low:
                    block.state = "TOUCHED"
                    block.touch_index = index
                    self.blocks_touched += 1
            elif block.state == "TOUCHED":
                elapsed = index - block.touch_index
                if elapsed < 1:
                    continue
                if self._reaction_ok(block, index) and index + 1 < len(self.data):
                    if self.pending is None and self.position is None:
                        self.pending = (block, index)
                        self.signals_confirmed += 1
                        continue
                if elapsed >= self.parameters.reaction_window:
                    block.state = "REJECTED"
                    self.reaction_rejections += 1
            if block.state in {"ACTIVE", "TOUCHED"}:
                remaining_blocks.append(block)
        self.active_blocks = remaining_blocks

    def run(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        first_index = self.parameters.atr_period + self.parameters.max_candles + self.parameters.bos_lookback + 1
        for index in range(first_index, len(self.data)):
            self.open_pending_position(index)
            self.manage_position(index)
            self.update_blocks(index)
            impulse = self.detect_impulse(index)
            if impulse is not None:
                direction, impulse_start = impulse
                self.create_block(index, direction, impulse_start)
            self.equity.append(self.capital)

        if self.position is not None:
            self.close_position(len(self.data) - 1, self.closes[-1], "END")
        equity = self.data.iloc[first_index:].loc[:, ["time", "close"]].copy()
        equity["capital"] = self.equity
        return pd.DataFrame(self.trades), equity


def make_summary(strategy: Strategy, trades: pd.DataFrame) -> dict:
    pnl = trades["pnl_usd"] if not trades.empty else pd.Series(dtype=float)
    winners = pnl[pnl > 0]
    losers = pnl[pnl < 0]
    profit_factor = float(winners.sum() / abs(losers.sum())) if not losers.empty else None
    capital = np.asarray(strategy.equity, dtype=float)
    peak = np.maximum.accumulate(capital)
    drawdown = (capital - peak) / peak if len(capital) else np.array([0.0])
    return {
        "model": "M0 - directional impulse, first retest and reaction only",
        "parameters": asdict(strategy.parameters),
        "impulses_detected": strategy.impulses_detected,
        "blocks_created": len(strategy.blocks),
        "blocks_touched": strategy.blocks_touched,
        "filter_rejections": strategy.filter_rejections,
        "signals_confirmed": strategy.signals_confirmed,
        "reaction_rejections": strategy.reaction_rejections,
        "entry_rejections": strategy.entry_rejections,
        "trades_closed": len(trades),
        "wins": int((pnl > 0).sum()),
        "losses": int((pnl < 0).sum()),
        "break_even": int((trades["reason"] == "BE").sum()) if not trades.empty else 0,
        "win_rate_pct": float((pnl > 0).mean() * 100.0) if not trades.empty else 0.0,
        "profit_factor": profit_factor,
        "expectancy_usd": float(pnl.mean()) if not pnl.empty else 0.0,
        "net_profit_usd": float(pnl.sum()) if not pnl.empty else 0.0,
        "final_capital_usd": strategy.capital,
        "max_drawdown_pct": float(drawdown.min() * 100.0),
    }


def make_subset_summary(trades: pd.DataFrame, label: str) -> dict:
    pnl = trades["pnl_usd"] if not trades.empty else pd.Series(dtype=float)
    winners = pnl[pnl > 0]
    losers = pnl[pnl < 0]
    return {
        f"{label}_trades": len(trades),
        f"{label}_net_profit_usd": float(pnl.sum()) if not pnl.empty else 0.0,
        f"{label}_expectancy_usd": float(pnl.mean()) if not pnl.empty else 0.0,
        f"{label}_win_rate_pct": float((pnl > 0).mean() * 100.0) if not trades.empty else 0.0,
        f"{label}_profit_factor": float(winners.sum() / abs(losers.sum())) if not losers.empty else None,
    }


def add_is_oos_metrics(summary: dict, trades: pd.DataFrame, data_length: int) -> dict:
    if trades.empty:
        is_trades = trades
        oos_trades = trades
    else:
        chunk = data_length // 4
        is_mask = (
            (trades["entry_index"] < chunk)
            | ((trades["entry_index"] >= 2 * chunk) & (trades["entry_index"] < 3 * chunk))
        )
        is_trades = trades[is_mask]
        oos_trades = trades[~is_mask]
    summary.update(make_subset_summary(is_trades, "is"))
    summary.update(make_subset_summary(oos_trades, "oos"))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest causal Model A v2.1 sur EURUSD M1.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results")
    parser.add_argument("--atr-base-pips", type=float, default=10.0)
    parser.add_argument("--atr-multiplier", type=float, default=1.5)
    parser.add_argument("--bos-mode", choices=("directional", "sweep_reclaim"), default="directional")
    parser.add_argument("--reaction-atr-multiplier", type=float, default=0.5)
    parser.add_argument("--reaction-min-pips", type=float, default=0.5)
    parser.add_argument("--reaction-window", type=int, default=3, choices=(1, 3, 5))
    parser.add_argument("--structure-grid", action="store_true")
    parser.add_argument("--reaction-grid", action="store_true")
    parser.add_argument("--filter-oos", action="store_true")
    parser.add_argument("--fvg-grid", action="store_true")
    parser.add_argument("--cost-grid", action="store_true")
    parser.add_argument("--rr", type=float, default=2.0)
    args = parser.parse_args()

    if args.cost_grid:
        data = add_atr(load_data(args.csv), Parameters().atr_period)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        summaries = []
        for total_cost_pips in (0.0, 0.5, 1.0, 2.0, 3.2):
            parameters = Parameters(
                atr_base_pips=args.atr_base_pips,
                atr_multiplier=args.atr_multiplier,
                bos_mode=args.bos_mode,
                reaction_atr_multiplier=args.reaction_atr_multiplier,
                reaction_min_pips=args.reaction_min_pips,
                reaction_window=args.reaction_window,
                spread_pips=0.0,
                commission_pips=0.0,
                slippage_pips=total_cost_pips,
                rr=args.rr,
            )
            strategy = Strategy(data, parameters)
            trades, equity = strategy.run()
            summary = add_is_oos_metrics(make_summary(strategy, trades), trades, len(data))
            summary["model"] = "M0_Cost_Sensitivity"
            summary["total_cost_pips"] = total_cost_pips
            summaries.append(summary)
            run_directory = args.output_dir / "cost_grid" / f"cost_{total_cost_pips:.2f}".replace(".", "_")
            run_directory.mkdir(parents=True, exist_ok=True)
            trades.to_csv(run_directory / "trades.csv", index=False)
            equity.to_csv(run_directory / "equity.csv", index=False)
            with (run_directory / "summary.json").open("w", encoding="ascii") as output:
                json.dump(summary, output, indent=2, allow_nan=False)
            print(
                f"M0 cost={total_cost_pips:.2f}: total={summary['trades_closed']} "
                f"PnL={summary['net_profit_usd']:.2f} OOS={summary['oos_trades']} "
                f"OOS_PnL={summary['oos_net_profit_usd']:.2f}"
            )
        pd.DataFrame(summaries).drop(columns="parameters").to_csv(
            args.output_dir / "cost_grid_oos_summary.csv", index=False
        )
        print(f"cost_grid_file: {args.output_dir / 'cost_grid_oos_summary.csv'}")
        return

    if args.fvg_grid:
        data = add_atr(load_data(args.csv), Parameters().atr_period)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        summaries = []
        for fvg_multiplier in (0.0, 0.5, 1.0):
            for fvg_min_pips in (0.5, 1.0, 1.5, 2.0, 3.0):
                parameters = Parameters(
                    atr_base_pips=args.atr_base_pips,
                    atr_multiplier=args.atr_multiplier,
                    bos_mode=args.bos_mode,
                    use_fvg=True,
                    fvg_atr_multiplier=fvg_multiplier,
                    fvg_min_pips=fvg_min_pips,
                    reaction_atr_multiplier=args.reaction_atr_multiplier,
                    reaction_min_pips=args.reaction_min_pips,
                    reaction_window=args.reaction_window,
                    rr=args.rr,
                )
                strategy = Strategy(data, parameters)
                trades, equity = strategy.run()
                summary = add_is_oos_metrics(make_summary(strategy, trades), trades, len(data))
                summary["model"] = "M1_FVG"
                summaries.append(summary)
                suffix = f"fvg_atr_{fvg_multiplier:.2f}_min_{fvg_min_pips:.2f}".replace(".", "_")
                run_directory = args.output_dir / "fvg_grid" / suffix
                run_directory.mkdir(parents=True, exist_ok=True)
                trades.to_csv(run_directory / "trades.csv", index=False)
                equity.to_csv(run_directory / "equity.csv", index=False)
                with (run_directory / "summary.json").open("w", encoding="ascii") as output:
                    json.dump(summary, output, indent=2, allow_nan=False)
                print(
                    f"M1_FVG atr={fvg_multiplier:.2f} min={fvg_min_pips:.2f}: "
                    f"total={summary['trades_closed']} IS={summary['is_trades']} "
                    f"OOS={summary['oos_trades']} OOS_PnL={summary['oos_net_profit_usd']:.2f}"
                )
        pd.DataFrame(summaries).drop(columns="parameters").to_csv(
            args.output_dir / "fvg_grid_oos_summary.csv", index=False
        )
        print(f"fvg_grid_file: {args.output_dir / 'fvg_grid_oos_summary.csv'}")
        return

    if args.filter_oos:
        data = add_atr(load_data(args.csv), Parameters().atr_period)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        models = (
            ("M0", {}),
            ("M1_FVG", {"use_fvg": True}),
            ("M2_FVG_Swing", {"use_fvg": True, "use_swing": True}),
            ("M3_FVG_Swing_Extremum", {"use_fvg": True, "use_swing": True, "use_extremum": True}),
            ("M4_All_Filters", {"use_fvg": True, "use_swing": True, "use_extremum": True, "use_trading_window": True}),
        )
        summaries = []
        for model_name, filters in models:
            parameters = Parameters(
                atr_base_pips=args.atr_base_pips,
                atr_multiplier=args.atr_multiplier,
                bos_mode=args.bos_mode,
                reaction_atr_multiplier=args.reaction_atr_multiplier,
                reaction_min_pips=args.reaction_min_pips,
                reaction_window=args.reaction_window,
                rr=args.rr,
                **filters,
            )
            strategy = Strategy(data, parameters)
            trades, equity = strategy.run()
            summary = add_is_oos_metrics(make_summary(strategy, trades), trades, len(data))
            summary["model"] = model_name
            summaries.append(summary)
            model_directory = args.output_dir / model_name.lower()
            model_directory.mkdir(exist_ok=True)
            trades.to_csv(model_directory / "trades.csv", index=False)
            equity.to_csv(model_directory / "equity.csv", index=False)
            with (model_directory / "summary.json").open("w", encoding="ascii") as output:
                json.dump(summary, output, indent=2, allow_nan=False)
            print(
                f"{model_name}: total={summary['trades_closed']} "
                f"IS={summary['is_trades']} OOS={summary['oos_trades']} "
                f"OOS_PnL={summary['oos_net_profit_usd']:.2f}"
            )
        pd.DataFrame(summaries).drop(columns="parameters").to_csv(
            args.output_dir / "filter_oos_summary.csv", index=False
        )
        print(f"oos_file: {args.output_dir / 'filter_oos_summary.csv'}")
        return

    reaction_settings = (
        ((0.0, 0.0), (0.0, 0.25), (0.0, 0.5), (0.0, 1.0),
         (0.25, 0.0), (0.25, 0.25), (0.25, 0.5), (0.25, 1.0),
         (0.5, 0.0), (0.5, 0.25), (0.5, 0.5), (0.5, 1.0))
        if args.reaction_grid
        else ((args.reaction_atr_multiplier, args.reaction_min_pips),)
    )
    reaction_windows = (1, 3, 5) if args.structure_grid else (args.reaction_window,)
    data = add_atr(load_data(args.csv), Parameters().atr_period)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for reaction_window in reaction_windows:
        for reaction_multiplier, reaction_floor in reaction_settings:
            parameters = Parameters(
            atr_base_pips=args.atr_base_pips,
            atr_multiplier=args.atr_multiplier,
            bos_mode=args.bos_mode,
            reaction_atr_multiplier=reaction_multiplier,
            reaction_min_pips=reaction_floor,
            reaction_window=reaction_window,
            rr=args.rr,
            )
            strategy = Strategy(data, parameters)
            trades, equity = strategy.run()
            summary = make_summary(strategy, trades)
            summaries.append(summary)
            suffix = (
                f"{args.bos_mode}_window_{reaction_window}_atr_{reaction_multiplier:.2f}_min_{reaction_floor:.2f}"
                .replace(".", "_")
            )
            run_directory = args.output_dir / suffix
            run_directory.mkdir(exist_ok=True)
            trades.to_csv(run_directory / "model_m0_trades.csv", index=False)
            equity.to_csv(run_directory / "model_m0_equity.csv", index=False)
            with (run_directory / "model_m0_summary.json").open("w", encoding="ascii") as output:
                json.dump(summary, output, indent=2, allow_nan=False)
            print(
                f"=== M0 bos_mode={args.bos_mode} reaction_window={reaction_window} "
                f"reaction_atr_multiplier={reaction_multiplier:.2f} reaction_min_pips={reaction_floor:.2f} ==="
            )
            for key, value in summary.items():
                if key != "parameters":
                    print(f"{key}: {value}")

    if args.reaction_grid or args.structure_grid:
        pd.DataFrame(summaries).drop(columns="parameters").to_csv(
            args.output_dir / "m0_structure_grid_summary.csv", index=False
        )
        print(f"grid_file: {args.output_dir / 'm0_structure_grid_summary.csv'}")


if __name__ == "__main__":
    main()#!/usr/bin/env python3
"""
Backtest Strategy: Order Blocks Retest
Version: 2.1 (Adaptive Thresholds for Low Volatility)
Date: 2026-09-03

Environment: mamba scalping_env
Python: 3.13.14
Pandas: 3.0.5
Numpy: 2.5.2
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
from datetime import datetime
import sys

# ============================================================================
# ENUMS & CLASSES
# ============================================================================

class OrderBlockState(Enum):
    """States d'une zone source"""
    ACTIVE = "ACTIVE"
    TOUCHED = "TOUCHED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"

class PositionDirection(Enum):
    """Direction position"""
    LONG = "long"
    SHORT = "short"

@dataclass
class Candle:
    """Représentation d'une bougie"""
    idx: int
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    tickvol: int
    spread: int
    
    def __post_init__(self):
        self.range = self.high - self.low

@dataclass
class OrderBlock:
    """Représentation d'une zone source (Order Block)"""
    t_created: int
    z_low: float
    z_high: float
    direction: PositionDirection
    
    # État
    state: OrderBlockState = field(default=OrderBlockState.ACTIVE)
    t_touch: Optional[int] = field(default=None)
    touch_count: int = field(default=0)
    
    # Score filtres
    score: int = field(default=0)
    filters: Dict = field(default_factory=dict)
    
    # Position liée
    position: Optional['Position'] = field(default=None)

@dataclass
class Position:
    """Représentation d'une position ouverte"""
    t_entry: int
    entry_price: float
    sl: float
    tp: float
    lots: float
    direction: PositionDirection
    block: OrderBlock
    
    # Stats
    pnl_pips: float = 0.0
    pnl_usd: float = 0.0
    reason_close: Optional[str] = None
    t_close: Optional[int] = None

@dataclass
class Trade:
    """Représentation d'un trade fermé"""
    t_entry: int
    entry_price: float
    t_close: int
    close_price: float
    direction: PositionDirection
    pnl_pips: float
    pnl_usd: float
    reason: str
    lots: float
    
    def __repr__(self):
        return f"Trade({self.direction.value} @ {self.entry_price:.5f} → {self.close_price:.5f}, PnL={self.pnl_usd:+.2f})"

# ============================================================================
# STRATEGY CLASS
# ============================================================================

class StrategyOrderBlocks:
    """Backtest stratégie Order Blocks Retest - Version 2.1 (Adaptive)"""
    
    def __init__(self, params: Dict):
        """
        Initialise stratégie avec paramètres
        
        Args:
            params: dictionnaire de paramètres
                - atr_multiplier: multiplicateur ATR pour amplitude
                - atr_base_pips: amplitude minimale en pips
                - max_candles: max bougies pour impulsion
                - bos_lookback: lookback pour BOS
                - fvg_multiplier: multiplicateur ATR pour FVG
                - fvg_min_pips: gap FVG minimum en pips
                - fractal_periods: période fractal pour swing
                - extremum_lookback: lookback pour extrême structurel
                - buffer_multiplier: multiplicateur ATR pour buffer SL
                - buffer_min_pips: buffer minimum en pips
                - min_stars: score minimum pour trade
                - capital: capital de départ
                - risk_pct: risque par trade (%)
                - rr: reward ratio (RR)
                - trading_hours: tuple (start_hour, end_hour) UTC
        """
        self.params = params
        
        # Data
        self.candles: List[Candle] = []
        self.atr_20: np.ndarray = np.array([])
        
        # Zones et positions
        self.order_blocks: List[OrderBlock] = []
        self.open_positions: List[Position] = []
        self.closed_trades: List[Trade] = []
        
        # Stats
        self.equity = []
        self.cash = params['capital']
        
        print(f"✅ Strategy initialized with params:")
        for k, v in params.items():
            if k != 'capital':
                print(f"   {k}: {v}")
    
    def load_data(self, csv_path: str) -> None:
        """Charge données CSV"""
        print(f"\n📂 Chargement: {csv_path}")
        
        df = pd.read_csv(csv_path, sep='\t')
        print(f"✅ {len(df)} bougies chargées")
        
        self.candles = [
            Candle(
                idx=i,
                timestamp=f"{row['<DATE>']} {row['<TIME>']}",
                open=row['<OPEN>'],
                high=row['<HIGH>'],
                low=row['<LOW>'],
                close=row['<CLOSE>'],
                tickvol=row['<TICKVOL>'],
                spread=row['<SPREAD>']
            )
            for i, (_, row) in enumerate(df.iterrows())
        ]
        
        # Calculer ATR_20
        ranges = np.array([c.range for c in self.candles])
        self.atr_20 = pd.Series(ranges).rolling(window=20).mean().values
        
        print(f"✅ ATR_20 calculé (median: {np.nanmedian(self.atr_20)*10000:.1f} pips)")
    
    # ========================================================================
    # DÉTECTION IMPULSIONS
    # ========================================================================
    
    def _compute_atr_at(self, t: int) -> float:
        """Retourne ATR_20 à l'indice t"""
        if t < 20 or np.isnan(self.atr_20[t]):
            return 0.00010  # Default 1 pip
        return self.atr_20[t]
    
    def detect_impulse(self, t: int) -> Tuple[Optional[PositionDirection], Optional[int], Optional[int]]:
        """
        Détecte si la bougie t termine une impulsion
        
        Retourne: (direction, t0_start, t_bos_broken) ou (None, None, None)
        """
        if t < self.params['max_candles'] + 10:
            return None, None, None
        
        candle_t = self.candles[t]
        
        # === IMPULSE UP ===
        # 1. Chercher plus bas local dans [t-max_candles, t]
        start_search = max(0, t - self.params['max_candles'])
        lows = [self.candles[i].low for i in range(start_search, t+1)]
        t0_local = np.argmin(lows)
        t0 = start_search + t0_local
        low_start = self.candles[t0].low
        
        # 2. AMPLITUDE ADAPTATIVE
        amplitude = candle_t.close - low_start
        atr = self._compute_atr_at(t)
        min_amplitude = max(
            self.params['atr_multiplier'] * atr,
            self.params['atr_base_pips'] / 10000
        )
        amplitude_ok = amplitude >= min_amplitude
        
        if not amplitude_ok:
            return None, None, None
        
        # 3. VITESSE
        speed_ok = (t - t0) <= self.params['max_candles']
        if not speed_ok:
            return None, None, None
        
        # 4. BOS (Break Of Structure)
        bos_start = max(0, t0 - self.params['bos_lookback'])
        bos_lows = [self.candles[i].low for i in range(bos_start, t0)]
        if len(bos_lows) == 0:
            return None, None, None
        
        swing_low = min(bos_lows)
        t_bos = bos_start + np.argmin(bos_lows)
        
        bos_ok = (candle_t.low < swing_low < candle_t.close)
        if not bos_ok:
            return None, None, None
        
        # 5. PAS DE CONTINUATION
        if t >= 2:
            cont_ok = not (
                self.candles[t-2].close > self.candles[t-2].open and
                self.candles[t-1].close > self.candles[t-1].open
            )
            if not cont_ok:
                return None, None, None
        
        return PositionDirection.LONG, t0, t_bos
    
    # ========================================================================
    # ZONE SOURCE
    # ========================================================================
    
    def get_zone_bounds(self, t_before_impulse: int) -> Tuple[float, float]:
        """
        Retourne les bornes de la zone source
        Variant B (wick): [low, high] de la bougie
        """
        c = self.candles[t_before_impulse]
        z_low = c.low
        z_high = c.high
        return z_low, z_high
    
    def create_order_block(self, t: int, direction: PositionDirection, t0: int) -> OrderBlock:
        """Crée un OrderBlock"""
        t_before = t0 - 1
        if t_before < 0:
            return None
        
        z_low, z_high = self.get_zone_bounds(t_before)
        
        block = OrderBlock(
            t_created=t,
            z_low=z_low,
            z_high=z_high,
            direction=direction
        )
        
        return block
    
    # ========================================================================
    # FILTRES
    # ========================================================================
    
    def compute_filters(self, block: OrderBlock, t: int) -> int:
        """Calcule score (4 filtres)"""
        score = 0
        filters_dict = {}
        
        # F1: FVG (Fair Value Gap)
        f1_fvg = self._check_filter_fvg(block, t)
        if f1_fvg:
            score += 1
            filters_dict['fvg'] = True
        else:
            filters_dict['fvg'] = False
        
        # F2: Swing (Fractal)
        f2_swing = self._check_filter_swing(block, t)
        if f2_swing:
            score += 1
            filters_dict['swing'] = True
        else:
            filters_dict['swing'] = False
        
        # F3: Extrême Structurel
        f3_extremum = self._check_filter_extremum(block, t)
        if f3_extremum:
            score += 1
            filters_dict['extremum'] = True
        else:
            filters_dict['extremum'] = False
        
        # F5: Fenêtre Trading
        f5_window = self._check_filter_window(block.t_created)
        if f5_window:
            score += 1
            filters_dict['window'] = True
        else:
            filters_dict['window'] = False
        
        block.score = score
        block.filters = filters_dict
        
        return score
    
    def _check_filter_fvg(self, block: OrderBlock, t: int) -> bool:
        """Filtre 1: FVG adaptatif"""
        t_before = block.t_created - 1
        t_after = t_before + 1
        
        if t_before < 0 or t_after >= len(self.candles):
            return False
        
        gap = self.candles[t_after].low - self.candles[t_before].high
        
        atr = self._compute_atr_at(t_before)
        min_gap = max(
            self.params['fvg_multiplier'] * atr,
            self.params['fvg_min_pips'] / 10000
        )
        
        return gap >= min_gap
    
    def _check_filter_swing(self, block: OrderBlock, t: int) -> bool:
        """Filtre 2: Swing (Fractal 5-bougies)"""
        t_before = block.t_created - 1
        
        if t_before < 2 or t_before + 2 >= len(self.candles):
            return False
        
        c = self.candles[t_before]
        
        # Fractal: low[t] < low[t-2], low[t-1], low[t+1], low[t+2]
        is_fractal_low = (
            c.low < self.candles[t_before-2].low and
            c.low < self.candles[t_before-1].low and
            c.low < self.candles[t_before+1].low and
            c.low < self.candles[t_before+2].low
        )
        
        return is_fractal_low
    
    def _check_filter_extremum(self, block: OrderBlock, t: int) -> bool:
        """Filtre 3: Extrême Structurel"""
        t_before = block.t_created - 1
        
        lookback = self.params['extremum_lookback']
        start = max(0, t_before - lookback)
        
        if start >= t_before:
            return False
        
        min_low = min([self.candles[i].low for i in range(start, t_before+1)])
        
        return self.candles[t_before].low == min_low
    
    def _check_filter_window(self, t_created: int) -> bool:
        """Filtre 5: Fenêtre de trading (8-22h UTC, lun-ven)"""
        c = self.candles[t_created]
        ts_str = c.timestamp  # Format: "2026.05.27 06:10:00"
        
        try:
            dt = pd.to_datetime(ts_str, format="%Y.%m.%d %H:%M:%S")
            hour = dt.hour
            dow = dt.dayofweek  # 0=Lun, 4=Ven
            
            start_hour, end_hour = self.params['trading_hours']
            
            return (start_hour <= hour <= end_hour) and (0 <= dow < 5)
        except:
            return False
    
    # ========================================================================
    # DETECTION REVISITE & ENTRÉE
    # ========================================================================
    
    def check_touch_and_reaction(self, block: OrderBlock, t: int) -> bool:
        """
        Vérifie si zone est touchée et réaction OK
        Retourne True si trade doit être entré à t+1
        """
        candle_t = self.candles[t]
        
        # Vérifier touche
        touch = (candle_t.low <= block.z_high and candle_t.high >= block.z_low)
        
        if not touch:
            return False
        
        block.touch_count += 1
        
        if block.touch_count != 1:
            return False  # Pas 1ère revisite
        
        block.t_touch = t
        block.state = OrderBlockState.TOUCHED
        
        # Vérifier réaction bougie suivante
        if t + 1 >= len(self.candles):
            return False
        
        candle_next = self.candles[t + 1]
        
        if block.direction == PositionDirection.LONG:
            reaction_ok = (
                candle_next.close > candle_next.open and
                candle_next.close > (block.z_high + 0.0002)  # 2 pips
            )
        else:
            reaction_ok = (
                candle_next.close < candle_next.open and
                candle_next.close < (block.z_low - 0.0002)  # 2 pips
            )
        
        return reaction_ok
    
    def enter_trade(self, block: OrderBlock, t: int) -> None:
        """Entre un trade à t+1 ouverture"""
        if t + 1 >= len(self.candles):
            return
        
        candle_entry = self.candles[t + 1]
        entry_price = candle_entry.open
        
        # SL & TP adaptatifs
        atr = self._compute_atr_at(t + 1)
        buffer = max(
            self.params['buffer_multiplier'] * atr,
            self.params['buffer_min_pips'] / 10000
        )
        
        if block.direction == PositionDirection.LONG:
            sl = block.z_low - buffer
            distance_sl = entry_price - sl
            tp = entry_price + (self.params['rr'] * distance_sl)
        else:
            sl = block.z_high + buffer
            distance_sl = sl - entry_price
            tp = entry_price - (self.params['rr'] * distance_sl)
        
        # Taille position
        lots = self._compute_position_size(entry_price, sl)
        
        if lots <= 0:
            return  # Trade trop petit
        
        # Créer position
        position = Position(
            t_entry=t + 1,
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            lots=lots,
            direction=block.direction,
            block=block
        )
        
        block.position = position
        self.open_positions.append(position)
    
    def _compute_position_size(self, entry: float, sl: float, capital: float = None) -> float:
        """Calcule taille position avec frais"""
        if capital is None:
            capital = self.params['capital']
        
        risk_amount = capital * self.params['risk_pct']
        
        # Frais totaux
        total_fees = (
            self.params.get('spread_pips', 1.2) +
            self.params.get('commission_pips', 1.0) +
            self.params.get('slippage_pips', 1.0)
        ) / 10000
        
        distance = abs(entry - sl) + total_fees
        
        if distance <= 0:
            return 0
        
        # Lots = risk_amount / (distance × pip_value)
        # Pour EURUSD: 1 lot = 100k unités = 10 USD par pip
            distance_pips = distance * 10000  # Convert distance to pips
            lots = risk_amount / (distance_pips * 10)
        
        # Arrondir à 0.01 lot
        lots = int(lots * 100) / 100
        
        return max(0, lots)
    
    # ========================================================================
    # GESTION POSITIONS
    # ========================================================================
    
    def update_positions(self, t: int) -> None:
        """Met à jour positions ouvertes"""
        candle = self.candles[t]
        
        for pos in self.open_positions[:]:
            # Vérifier SL
            if pos.direction == PositionDirection.LONG:
                if candle.low <= pos.sl:
                    self._close_position(pos, pos.sl, 'SL', t)
                    self.open_positions.remove(pos)
                    continue
                
                # Vérifier TP
                if candle.high >= pos.tp:
                    self._close_position(pos, pos.tp, 'TP', t)
                    self.open_positions.remove(pos)
                    continue
            else:
                if candle.high >= pos.sl:
                    self._close_position(pos, pos.sl, 'SL', t)
                    self.open_positions.remove(pos)
                    continue
                
                if candle.low <= pos.tp:
                    self._close_position(pos, pos.tp, 'TP', t)
                    self.open_positions.remove(pos)
                    continue
    
    def _close_position(self, pos: Position, close_price: float, reason: str, t: int) -> None:
        """Ferme une position"""
        # PnL en pips
        if pos.direction == PositionDirection.LONG:
            pnl_pips = (close_price - pos.entry_price) * 10000
        else:
            pnl_pips = (pos.entry_price - close_price) * 10000
        
        # PnL en USD (1 lot EURUSD = 10 USD par pip)
        pnl_usd = pnl_pips * pos.lots * 10
        
        trade = Trade(
            t_entry=pos.t_entry,
            entry_price=pos.entry_price,
            t_close=t,
            close_price=close_price,
            direction=pos.direction,
            pnl_pips=pnl_pips,
            pnl_usd=pnl_usd,
            reason=reason,
            lots=pos.lots
        )
        
        self.closed_trades.append(trade)
        self.cash += pnl_usd
        self.equity.append(self.cash)
    
    # ========================================================================
    # BOUCLE PRINCIPALE
    # ========================================================================
    
    def backtest(self) -> None:
        """Exécute le backtest"""
        print(f"\n🔄 Backtest en cours... ({len(self.candles)} bougies)")
        
        for t in range(len(self.candles)):
            # 1. Détecter impulsions
            direction, t0, t_bos = self.detect_impulse(t)
            if direction:
                block = self.create_order_block(t, direction, t0)
                if block:
                    self.compute_filters(block, t)
                    self.order_blocks.append(block)
            
            # 2. Mettre à jour zones
            for block in self.order_blocks:
                if block.state == OrderBlockState.ACTIVE:
                    # Chercher 1ère revisite
                    if self.check_touch_and_reaction(block, t):
                        # Vérifier score
                        if block.score >= self.params['min_stars']:
                            self.enter_trade(block, t)
                            block.state = OrderBlockState.CONFIRMED
                    
                    # Expiration
                    if (t - block.t_created) > 500:
                        block.state = OrderBlockState.EXPIRED
            
            # 3. Mettre à jour positions
            self.update_positions(t)
            
            # Afficher progress
            if (t + 1) % 10000 == 0:
                print(f"  {t+1}/{len(self.candles)} ({(t+1)/len(self.candles)*100:.1f}%) - "
                      f"Zones: {len(self.order_blocks)}, Trades: {len(self.closed_trades)}")
        
        # Fermer positions ouvertes
        last_t = len(self.candles) - 1
        for pos in self.open_positions[:]:
            close_price = self.candles[last_t].close
            self._close_position(pos, close_price, 'END', last_t)
        
        print(f"✅ Backtest terminé")
    
    # ========================================================================
    # RAPPORTS
    # ========================================================================
    
    def generate_report(self) -> Dict:
        """Génère rapport de backtest"""
        if not self.closed_trades:
            return {"error": "Aucun trade exécuté"}
        
        trades_df = pd.DataFrame([
            {
                'entry': t.entry_price,
                'close': t.close_price,
                'direction': t.direction.value,
                'pnl_pips': t.pnl_pips,
                'pnl_usd': t.pnl_usd,
                'lots': t.lots,
                'reason': t.reason
            }
            for t in self.closed_trades
        ])
        
        # Statistiques
        total_trades = len(self.closed_trades)
        wins = (trades_df['pnl_usd'] > 0).sum()
        losses = (trades_df['pnl_usd'] < 0).sum()
        breakeven = (trades_df['pnl_usd'] == 0).sum()
        
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        gains = trades_df[trades_df['pnl_usd'] > 0]['pnl_usd'].sum()
        pertes = abs(trades_df[trades_df['pnl_usd'] < 0]['pnl_usd'].sum())
        
        pf = gains / pertes if pertes > 0 else 0
        
        avg_win = trades_df[trades_df['pnl_usd'] > 0]['pnl_usd'].mean() if wins > 0 else 0
        avg_loss = trades_df[trades_df['pnl_usd'] < 0]['pnl_usd'].mean() if losses > 0 else 0
        
        total_pnl = trades_df['pnl_usd'].sum()
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        
        report = {
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'breakeven': breakeven,
            'win_rate': win_rate,
            'profit_factor': pf,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_pnl': total_pnl,
            'total_pnl_pips': trades_df['pnl_pips'].sum(),
            'expectancy': expectancy,
            'initial_capital': self.params['capital'],
            'final_capital': self.cash,
            'return_pct': (self.cash - self.params['capital']) / self.params['capital'] * 100,
            'order_blocks_created': len(self.order_blocks),
            'order_blocks_touched': sum(1 for b in self.order_blocks if b.touch_count > 0),
        }
        
        return report
    
    def print_report(self) -> None:
        """Affiche rapport formaté"""
        report = self.generate_report()
        
        if 'error' in report:
            print(f"\n❌ {report['error']}")
            return
        
        print(f"\n" + "=" * 80)
        print(f"BACKTEST REPORT")
        print(f"=" * 80)
        
        print(f"\n📊 TRADES")
        print(f"Total Trades:        {report['total_trades']}")
        print(f"  - Wins:            {report['wins']} ({report['win_rate']*100:.1f}%)")
        print(f"  - Losses:          {report['losses']}")
        print(f"  - Breakeven:       {report['breakeven']}")
        
        print(f"\n💰 P&L")
        print(f"Total P&L (USD):     {report['total_pnl']:+.2f}")
        print(f"Total P&L (pips):    {report['total_pnl_pips']:+.1f}")
        print(f"Expectancy (USD):    {report['expectancy']:+.2f}")
        print(f"Return (%):          {report['return_pct']:+.2f}%")
        
        print(f"\n📈 MÉTRIQUES")
        print(f"Profit Factor:       {report['profit_factor']:.2f}")
        print(f"Avg Win (USD):       {report['avg_win']:+.2f}")
        print(f"Avg Loss (USD):      {report['avg_loss']:+.2f}")
        
        print(f"\n🎯 ZONES")
        print(f"Order Blocks:        {report['order_blocks_created']}")
        print(f"Touched:             {report['order_blocks_touched']} ({report['order_blocks_touched']/max(1, report['order_blocks_created'])*100:.1f}%)")
        
        print(f"\n💵 CAPITAL")
        print(f"Initial:             ${report['initial_capital']:.2f}")
        print(f"Final:               ${report['final_capital']:+.2f}")
        
        print(f"\n" + "=" * 80)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__legacy_backtest__':
    # Paramètres par défaut (v2.1 - adaptatif)
    DEFAULT_PARAMS = {
        # Impulse Detection
        'atr_multiplier': 1.5,
        'atr_base_pips': 10,
        'max_candles': 20,
        'bos_lookback': 50,
        
        # Filtres
        'fvg_multiplier': 1.0,
        'fvg_min_pips': 5,
        'fractal_periods': 5,
        'extremum_lookback': 20,
        'trading_hours': (8, 22),
        'min_stars': 2,
        
        # Risk Management
        'buffer_multiplier': 1.0,
        'buffer_min_pips': 3,
        'capital': 10000,
        'risk_pct': 0.01,
        'rr': 2.0,
        'spread_pips': 1.2,
        'commission_pips': 1.0,
        'slippage_pips': 1.0,
    }
    
    # Créer stratégie
    strategy = StrategyOrderBlocks(DEFAULT_PARAMS)
    
    # Charger données
    csv_path = "EURUSD_M1_202605270610_202609011829.csv"
    strategy.load_data(csv_path)
    
    # Exécuter backtest
    strategy.backtest()
    
    # Générer rapport
    strategy.print_report()
    
    print(f"\n✅ Backtest terminé avec succès!")
