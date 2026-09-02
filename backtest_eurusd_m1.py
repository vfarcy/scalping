import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from datetime import datetime

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(OUTPUT_DIR, "EURUSD_M1_202605270610_202609011829.csv")

# Liste des dépendances externes requises sur l'ordinateur de l'utilisateur :
# pip install pandas numpy matplotlib

def load_mt5_csv(csv_path):
    """
    Charge un export MetaTrader 5 (colonnes séparées par tabulation :
    <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>)
    et le convertit au format attendu par le backtest (colonnes en minuscules,
    'time' en datetime unique). Retourne un tuple (DataFrame, meta).
    """
    print(f"Chargement des données depuis le fichier CSV : {csv_path}")
    df = pd.read_csv(csv_path, sep='\t')
    df.columns = [col.strip('<>').lower() for col in df.columns]
    df['time'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M:%S')
    df = df.drop(columns=['date'])
    meta = {
        'source': 'csv_mt5', 'source_detail': csv_path,
        'ticker': 'EURUSD', 'period': 'M1', 'interval': '1m',
    }
    return df, meta

def run_fibonacci_backtest(
    df, window=20, risk_reward=2.0, initial_capital=10000.0,
    risk_per_trade=0.01, spread=0.0, commission=0.0, slippage=0.0,
    point_value=1.0
):
    """
    Exécute le backtest de la stratégie de Fibonacci OTE.

    Pour un compte Axi Standard, commission doit rester à 0.0 : le coût
    principal est le spread variable, à fournir dans l'unité de prix.
    """
    trades = []
    capital = initial_capital
    initial_capital = capital
    equity_curve = []
    
    # 1. Calculer la tendance de fond (Moyenne Mobile Exponentielle 200)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    in_trade = False
    trade_info = {}
    pending_trade = None
    
    for i in range(window, len(df)):
        current_time = df['time'].iloc[i]
        current_open = df['open'].iloc[i]
        current_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        ema_200 = df['ema_200'].iloc[i]

        # Une détection sur la bougie précédente déclenche une entrée à l'ouverture suivante.
        if pending_trade is not None and not in_trade:
            # Le spread est facturé pour moitié à l'entrée (achat à l'ask / vente au bid) et pour moitié à la sortie.
            entry_spread_adj = spread / 2 if pending_trade['type'] == 'BUY' else -spread / 2
            pending_trade['entry_price'] = current_open + entry_spread_adj
            entry = pending_trade['entry_price']
            if (
                (pending_trade['type'] == 'BUY' and entry > pending_trade['sl']) or
                (pending_trade['type'] == 'SELL' and entry < pending_trade['sl'])
            ):
                risk_distance = abs(entry - pending_trade['sl'])
                total_cost_per_unit = 2 * slippage
                position_risk = (risk_distance + total_cost_per_unit) * point_value
                position_size = (capital * risk_per_trade / position_risk) if position_risk > 0 else 0.0
                pending_trade['position_size'] = position_size
                pending_trade['initial_sl'] = pending_trade['sl']
                pending_trade['entry_time'] = current_time
                trade_info = pending_trade
                in_trade = position_size > 0
            pending_trade = None
        
        if not in_trade:
            # Recherche d'opportunité d'achat (Tendance haussière)
            if current_close > ema_200:
                # Trouver le dernier Swing Low et Swing High récents pour tracer Fibonacci
                recent_lows = df['low'].iloc[max(0, i-window*2):i].values
                recent_highs = df['high'].iloc[max(0, i-window*2):i].values
                
                if len(recent_lows) > 0 and len(recent_highs) > 0:
                    start_point = np.min(recent_lows)  # 0% / 100% selon le sens
                    end_point = np.max(recent_highs)    # Sommet
                    
                    # On s'assure que le mouvement est impulsif et que le point bas s'est produit avant le point haut
                    idx_low = np.argmin(recent_lows)
                    idx_high = np.argmax(recent_highs)
                    
                    if idx_low < idx_high and (end_point - start_point) > 0.05 * current_close / 100:
                        diff = end_point - start_point
                        ote_entry = end_point - 0.62 * diff
                        sl_level = start_point - 0.02 * diff # Léger filtre sous le creux
                        tp_level = ote_entry + (ote_entry - sl_level) * risk_reward
                        bos_level = end_point # Cassure de structure
                        
                        # Si le prix actuel retrace dans la zone OTE
                        if current_low <= ote_entry and current_close > sl_level:
                            pending_trade = {
                                'type': 'BUY',
                                'sl': sl_level,
                                'tp': tp_level,
                                'bos': bos_level,
                                'be_triggered': False,
                                'signal_time': current_time
                            }
            
            # Recherche d'opportunité de vente (Tendance baissière)
            elif current_close < ema_200:
                recent_lows = df['low'].iloc[max(0, i-window*2):i].values
                recent_highs = df['high'].iloc[max(0, i-window*2):i].values
                
                if len(recent_lows) > 0 and len(recent_highs) > 0:
                    start_point = np.max(recent_highs)  # Sommet
                    end_point = np.min(recent_lows)    # Creux
                    
                    idx_high = np.argmax(recent_highs)
                    idx_low = np.argmin(recent_lows)
                    
                    if idx_high < idx_low and (start_point - end_point) > 0.05 * current_close / 100:
                        diff = start_point - end_point
                        ote_entry = end_point + 0.62 * diff
                        sl_level = start_point + 0.02 * diff # Léger filtre au-dessus du sommet
                        tp_level = ote_entry - (sl_level - ote_entry) * risk_reward
                        bos_level = end_point # Cassure de structure
                        
                        # Si le prix actuel retrace à la hausse dans la zone OTE
                        if current_high >= ote_entry and current_close < sl_level:
                            pending_trade = {
                                'type': 'SELL',
                                'sl': sl_level,
                                'tp': tp_level,
                                'bos': bos_level,
                                'be_triggered': False,
                                'signal_time': current_time
                            }
                            
        else:
            # Gestion du trade en cours
            t_type = trade_info['type']
            entry = trade_info['entry_price']
            sl = trade_info['sl']
            tp = trade_info['tp']
            bos = trade_info['bos']
            be = trade_info['be_triggered']
            position_size = trade_info['position_size']
            
            if t_type == 'BUY':
                # Vérifier si on doit sécuriser à Break Even (BOS)
                if not be and current_high >= bos:
                    trade_info['sl'] = entry  # SL déplacé au point d'entrée
                    trade_info['be_triggered'] = True
                    be = True
                
                # Sorties de trade
                if current_low <= trade_info['sl']:
                    # Perte ou sortie à BE
                    result = "BE" if be else "LOSS"
                    exit_price = trade_info['sl'] - slippage - spread / 2
                    gross_pnl = (exit_price - entry) * position_size * point_value
                    profit = gross_pnl - commission
                    capital += profit
                    trades.append({**trade_info, 'exit_price': exit_price, 'exit_time': current_time, 'result': result, 'profit': profit})
                    in_trade = False
                elif current_high >= tp:
                    # Gain
                    exit_price = tp - slippage - spread / 2
                    profit = (exit_price - entry) * position_size * point_value - commission
                    capital += profit
                    trades.append({**trade_info, 'exit_price': exit_price, 'exit_time': current_time, 'result': 'WIN', 'profit': profit})
                    in_trade = False
                    
            elif t_type == 'SELL':
                # Vérifier si on doit sécuriser à Break Even (BOS)
                if not be and current_low <= bos:
                    trade_info['sl'] = entry  # SL déplacé au point d'entrée
                    trade_info['be_triggered'] = True
                    be = True
                
                # Sorties de trade
                if current_high >= trade_info['sl']:
                    result = "BE" if be else "LOSS"
                    exit_price = trade_info['sl'] + slippage + spread / 2
                    gross_pnl = (entry - exit_price) * position_size * point_value
                    profit = gross_pnl - commission
                    capital += profit
                    trades.append({**trade_info, 'exit_price': exit_price, 'exit_time': current_time, 'result': result, 'profit': profit})
                    in_trade = False
                elif current_low <= tp:
                    # Gain
                    exit_price = tp + slippage + spread / 2
                    profit = (entry - exit_price) * position_size * point_value - commission
                    capital += profit
                    trades.append({**trade_info, 'exit_price': exit_price, 'exit_time': current_time, 'result': 'WIN', 'profit': profit})
                    in_trade = False

        # Une observation de capital est conservée pour chaque bougie afin que
        # le drawdown et le graphique restent alignés avec les dates.
        equity_curve.append(capital)

    df['capital'] = initial_capital
    df.loc[df.index[window:], 'capital'] = equity_curve
    return trades, df

def plot_and_save_results(df, trades, filename="backtest_eurusd_performance.png", asset_label="EUR/USD"):
    """
    Affiche et enregistre la courbe de croissance du capital.
    """
    plt.figure(figsize=(10, 6))
    plt.plot(df['time'], df['capital'], label="Courbe de Capital (€)", color="#cc5500", linewidth=2)
    plt.title(f"Performance du Backtest Fibonacci OTE — {asset_label}", fontsize=14, fontweight='bold', pad=15)
    plt.xlabel("Date", fontsize=11)
    plt.ylabel("Capital (€)", fontsize=11)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    
    # Annotation statistique
    wins = sum(1 for t in trades if t['result'] == 'WIN')
    losses = sum(1 for t in trades if t['result'] == 'LOSS')
    bes = sum(1 for t in trades if t['result'] == 'BE')
    total = len(trades)
    win_rate = (wins / total * 100) if total > 0 else 0
    final_cap = df['capital'].iloc[-1]
    net_profit = final_cap - 10000.0
    
    stats_text = (
        f"Trades Totaux: {total}\n"
        f"Gagnants (WIN): {wins} ({win_rate:.1f}%)\n"
        f"Perdants (LOSS): {losses}\n"
        f"Sécurisés (BE): {bes}\n"
        f"Profit Net: +{net_profit:.2f} €"
    )
    plt.gcf().text(0.15, 0.70, stats_text, fontsize=10, bbox=dict(facecolor='white', alpha=0.8, edgecolor='#cc5500'))
    
    plt.tight_layout()
    output_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Graphique sauvegardé sous : {output_path}")

def analyze_performance(df, trades, initial_capital=10000.0):
    """
    Calcule des indicateurs de performance avancés, affiche une interprétation
    textuelle de la stratégie (win rate, profit factor, drawdown, expectancy...)
    et retourne les statistiques calculées.
    """
    total = len(trades)
    if total == 0:
        print("\nAucun trade exécuté : aucune analyse de performance possible.")
        return {'total': 0}

    wins = [t['profit'] for t in trades if t['result'] == 'WIN']
    losses = [t['profit'] for t in trades if t['result'] == 'LOSS']
    bes = [t['profit'] for t in trades if t['result'] == 'BE']

    win_rate = len(wins) / total * 100
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    expectancy = (sum(t['profit'] for t in trades) / total)

    # Maximum drawdown sur la courbe de capital
    equity = df['capital'].values
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max * 100
    max_drawdown = drawdowns.min()

    final_capital = df['capital'].iloc[-1]
    net_profit = final_capital - initial_capital
    net_profit_pct = net_profit / initial_capital * 100

    stats = {
        'total': total, 'wins': len(wins), 'losses': len(losses), 'bes': len(bes),
        'win_rate': win_rate, 'profit_factor': profit_factor, 'avg_win': avg_win,
        'avg_loss': avg_loss, 'expectancy': expectancy, 'max_drawdown': max_drawdown,
        'net_profit': net_profit, 'net_profit_pct': net_profit_pct,
    }

    print("\n=== Analyse de performance ===")
    print(f"Trades totaux        : {total} (WIN: {len(wins)}, LOSS: {len(losses)}, BE: {len(bes)})")
    print(f"Win rate             : {win_rate:.1f}%")
    print(f"Profit factor        : {profit_factor:.2f}")
    print(f"Gain moyen / Perte moyenne : {avg_win:.2f} € / {avg_loss:.2f} €")
    print(f"Espérance par trade   : {expectancy:.2f} €")
    print(f"Drawdown maximum      : {max_drawdown:.2f}%")
    print(f"Profit net            : {net_profit:+.2f} € ({net_profit_pct:+.2f}%)")

    # Interprétation qualitative
    print("\n--- Interprétation ---")
    if profit_factor >= 1.5:
        print("- Profit factor solide : les gains couvrent largement les pertes.")
    elif profit_factor >= 1.0:
        print("- Profit factor tout juste positif : la stratégie est fragile, peu de marge de sécurité.")
    else:
        print("- Profit factor < 1 : la stratégie perd de l'argent sur cette période, à revoir.")

    if win_rate >= 50:
        print("- Win rate élevé, la stratégie gagne plus souvent qu'elle ne perd.")
    else:
        print("- Win rate faible : la rentabilité dépend d'un ratio gain/perte élevé plutôt que de la fréquence des gains.")

    if max_drawdown <= -20:
        print("- Drawdown important : le risque de perte en capital sur une séquence défavorable est élevé.")
    else:
        print("- Drawdown maîtrisé sur la période testée.")

    print("- Ces résultats portent sur l'échantillon disponible dans le fichier CSV : à confirmer sur une période plus longue avant toute conclusion définitive.")
    return stats

def _compute_bucket_stats(trades_subset):
    """Calcule win rate, profit factor et espérance pour un sous-ensemble de trades."""
    total = len(trades_subset)
    if total == 0:
        return {'total': 0}
    wins = [t['profit'] for t in trades_subset if t['result'] == 'WIN']
    losses = [t['profit'] for t in trades_subset if t['result'] == 'LOSS']
    bes = [t['profit'] for t in trades_subset if t['result'] == 'BE']
    win_rate = len(wins) / total * 100
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    net_profit = sum(t['profit'] for t in trades_subset)
    expectancy = net_profit / total
    return {
        'total': total, 'wins': len(wins), 'losses': len(losses), 'bes': len(bes),
        'win_rate': win_rate, 'profit_factor': profit_factor,
        'net_profit': net_profit, 'expectancy': expectancy,
    }

def _format_bucket(label, s):
    if s['total'] == 0:
        return f"{label:<22}: aucun trade"
    return (
        f"{label:<22}: {s['total']} trades | win rate {s['win_rate']:.1f}% "
        f"| profit factor {s['profit_factor']:.2f} | espérance {s['expectancy']:+.2f} € "
        f"| P&L net {s['net_profit']:+.2f} €"
    )

def analyze_session_performance(trades, session_start=(14, 30), session_end=(17, 0)):
    """
    Compare la performance des trades ouverts durant la session de volatilité
    américaine (par défaut 14h30-17h00, heure de New York) par rapport au reste
    de la journée. Les horodatages du fichier CSV MT5 sont supposés déjà dans
    ce fuseau ; à ajuster si le broker utilise un autre référentiel.
    """
    start_minutes = session_start[0] * 60 + session_start[1]
    end_minutes = session_end[0] * 60 + session_end[1]

    session_trades, other_trades = [], []
    for t in trades:
        minutes_of_day = t['entry_time'].hour * 60 + t['entry_time'].minute
        if start_minutes <= minutes_of_day <= end_minutes:
            session_trades.append(t)
        else:
            other_trades.append(t)

    session_stats = _compute_bucket_stats(session_trades)
    other_stats = _compute_bucket_stats(other_trades)

    label = f"{session_start[0]:02d}h{session_start[1]:02d}-{session_end[0]:02d}h{session_end[1]:02d}"
    print(f"\n=== Analyse par tranche horaire (session {label}) ===")
    print(_format_bucket("Session volatilité US", session_stats))
    print(_format_bucket("Reste de la journée", other_stats))

    if session_stats['total'] > 0 and other_stats['total'] > 0:
        if session_stats['profit_factor'] > other_stats['profit_factor'] and session_stats['expectancy'] > other_stats['expectancy']:
            print("- La stratégie performe mieux durant la session de volatilité américaine que sur le reste de la journée.")
        elif session_stats['profit_factor'] < other_stats['profit_factor'] and session_stats['expectancy'] < other_stats['expectancy']:
            print("- La stratégie performe moins bien durant la session de volatilité américaine que sur le reste de la journée.")
        else:
            print("- Résultats mitigés entre la session de volatilité américaine et le reste de la journée : pas de tendance nette.")
    else:
        print("- Échantillon insuffisant sur l'une des deux tranches pour conclure.")

    return {'label': label, 'session': session_stats, 'other': other_stats}

def generate_execution_log(meta, trades, stats, session_analysis=None, log_filename=None):
    """
    Génère un journal d'exécution détaillant, pour ce run, les 3 étapes de la
    stratégie : chargement des données, analyse structurelle/technique,
    et exécution/protection des trades (avec l'historique complet des trades).
    """
    timestamp = datetime.now()
    if log_filename is None:
        log_filename = f"journal_execution_{timestamp:%Y%m%d_%H%M%S}.log"
    log_path = os.path.join(OUTPUT_DIR, log_filename)

    source_labels = {
        'csv_mt5': f"Fichier CSV MetaTrader 5 local ({meta.get('source_detail')})",
    }

    lines = []
    lines.append("=== JOURNAL D'EXÉCUTION DU BACKTEST FIBONACCI OTE ===")
    lines.append(f"Date d'exécution : {timestamp:%Y-%m-%d %H:%M:%S}")

    lines.append("\n--- 1. Chargement des données ---")
    lines.append(f"Source des données : {source_labels.get(meta['source'], meta['source'])}")
    lines.append(f"Actif               : {meta['ticker']}")
    lines.append(f"Période / Unité de temps : {meta['period']} / {meta['interval']}")
    lines.append(f"Bougies récupérées  : {meta['n_candles']}")

    lines.append("\n--- 2. Analyse structurelle et technique ---")
    lines.append("Indicateur de tendance : EMA 200 sur le cours de clôture (biais haussier si close > EMA200, baissier sinon).")
    lines.append(f"Détection des points pivots : Swing Highs / Swing Lows sur une fenêtre glissante de {meta.get('window', 20)} bougies.")
    lines.append("Tracé Fibonacci : zone d'entrée optimale (OTE) au retracement de 62 % du dernier mouvement impulsif identifié.")
    lines.append(f"Opportunités validées et exécutées : {stats.get('total', 0)}")

    lines.append("\n--- 3. Exécution et protection ---")
    lines.append("Règles appliquées : entrée sur retracement dans la zone OTE (0.62), Stop Loss strict au dernier plus bas/haut (+ filtre de 2 %),")
    lines.append("Take Profit au ratio risque/rendement 1:2, sécurisation à Break Even (BE) dès que la structure de marché est cassée (BOS).")
    lines.append("\nDétail des trades :")
    if trades:
        for idx, t in enumerate(trades, start=1):
            be_str = "Oui" if t['be_triggered'] else "Non"
            lines.append(
                f"#{idx:03d} {t['type']:<4} | entrée {t['entry_time']} @ {t['entry_price']:.5f} "
                f"| SL {t['sl']:.5f} | TP {t['tp']:.5f} | BOS {t['bos']:.5f} | BE déclenché : {be_str} "
                f"| sortie {t['exit_time']} @ {t['exit_price']:.5f} | résultat {t['result']} | P&L {t['profit']:+.2f} €"
            )
    else:
        lines.append("Aucun trade exécuté durant cette période.")

    if stats.get('total', 0) > 0:
        lines.append("\n--- Résumé de performance ---")
        lines.append(f"Win rate      : {stats['win_rate']:.1f}% (WIN: {stats['wins']}, LOSS: {stats['losses']}, BE: {stats['bes']})")
        lines.append(f"Profit factor : {stats['profit_factor']:.2f}")
        lines.append(f"Espérance par trade : {stats['expectancy']:.2f} €")
        lines.append(f"Drawdown maximum    : {stats['max_drawdown']:.2f}%")
        lines.append(f"Profit net          : {stats['net_profit']:+.2f} € ({stats['net_profit_pct']:+.2f}%)")

    if session_analysis is not None:
        lines.append(f"\n--- 4. Analyse par tranche horaire (session {session_analysis['label']}) ---")
        lines.append(_format_bucket("Session volatilité US", session_analysis['session']))
        lines.append(_format_bucket("Reste de la journée", session_analysis['other']))
        s, o = session_analysis['session'], session_analysis['other']
        if s['total'] > 0 and o['total'] > 0:
            if s['profit_factor'] > o['profit_factor'] and s['expectancy'] > o['expectancy']:
                lines.append("La stratégie performe mieux durant la session de volatilité américaine que sur le reste de la journée.")
            elif s['profit_factor'] < o['profit_factor'] and s['expectancy'] < o['expectancy']:
                lines.append("La stratégie performe moins bien durant la session de volatilité américaine que sur le reste de la journée.")
            else:
                lines.append("Résultats mitigés entre la session de volatilité américaine et le reste de la journée : pas de tendance nette.")
        else:
            lines.append("Échantillon insuffisant sur l'une des deux tranches pour conclure.")

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Journal d'exécution sauvegardé sous : {log_path}")
    return log_path

if __name__ == "__main__":
    window = 20
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'=' * 20} BACKTEST : EUR/USD (M1, données CSV réelles) {'=' * 20}")
    data, meta = load_mt5_csv(CSV_PATH)
    meta['n_candles'] = len(data)
    meta['window'] = window

    # Spread réel moyen du fichier (colonne <SPREAD> en points, 1 point = 0.00001 pour l'EUR/USD).
    avg_spread_points = data['spread'].mean()
    spread_price = avg_spread_points * 0.00001
    print(f"Spread moyen observé : {avg_spread_points:.1f} points ({spread_price:.5f} en prix).")

    trades, df_result = run_fibonacci_backtest(
        data, window=window, spread=spread_price, slippage=0.0, commission=0.0
    )
    plot_and_save_results(df_result, trades, filename=f"backtest_eurusd_performance_{run_timestamp}.png", asset_label="EUR/USD")
    stats = analyze_performance(df_result, trades)
    session_analysis = analyze_session_performance(trades)
    generate_execution_log(meta, trades, stats, session_analysis=session_analysis,
                            log_filename=f"journal_execution_eurusd_{run_timestamp}.log")
    print("Backtest EUR/USD complété avec succès !")
