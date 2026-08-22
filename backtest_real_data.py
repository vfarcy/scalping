import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from datetime import datetime

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Liste des dépendances externes requises sur l'ordinateur de l'utilisateur :
# pip install pandas numpy matplotlib yfinance

def download_or_load_data(ticker="GC=F", period="1mo", interval="1h", csv_path=None):
    """
    Tente de télécharger de vraies données depuis Yahoo Finance.
    En cas d'échec (ex. pas d'internet dans le sandbox), charge un fichier CSV.
    Retourne un tuple (DataFrame, meta) où meta décrit la source des données utilisée.
    """
    if csv_path and os.path.exists(csv_path):
        print(f"Chargement des données depuis le fichier CSV : {csv_path}")
        df = pd.read_csv(csv_path)
        # S'assurer que les colonnes sont au bon format
        df['time'] = pd.to_datetime(df.iloc[:, 0])
        df.columns = [col.lower() for col in df.columns]
        meta = {'source': 'csv', 'source_detail': csv_path, 'ticker': ticker, 'period': period, 'interval': interval}
        return df, meta

    try:
        import yfinance as yf
        print(f"Téléchargement des données réelles pour {ticker} depuis Yahoo Finance ({interval})...")
        data = yf.download(tickers=ticker, period=period, interval=interval)
        if data.empty:
            raise ValueError("Aucune donnée téléchargée.")
        
        # Reset index pour avoir le temps en colonne
        data = data.reset_index()
        data.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in data.columns]
        data = data.rename(columns={'date': 'time', 'datetime': 'time', 'index': 'time'})
        print(f"Téléchargement réussi ! {len(data)} bougies récupérées.")
        meta = {'source': 'yahoo_live', 'source_detail': 'Yahoo Finance (yfinance)', 'ticker': ticker, 'period': period, 'interval': interval}
        return data, meta
    except Exception as e:
        print(f"Impossible de télécharger les données en direct ({e}).")
        # Fallback sur un fichier mock si on est dans le sandbox
        fallback_path = "mock_gold_data.csv"
        if os.path.exists(fallback_path):
            print("Utilisation du fichier de simulation local.")
            df = pd.read_csv(fallback_path)
            df['time'] = pd.to_datetime(df['time'])
            meta = {'source': 'csv_fallback', 'source_detail': fallback_path, 'ticker': ticker, 'period': period, 'interval': interval}
            return df, meta
        else:
            raise FileNotFoundError("Aucune source de données disponible.")

def run_fibonacci_backtest(df, window=20, risk_reward=2.0):
    """
    Exécute le backtest de la stratégie de Fibonacci OTE.
    """
    trades = []
    capital = 10000.0 # Capital de départ fictif
    initial_capital = capital
    equity_curve = [capital]
    dates = [df['time'].iloc[0]]
    
    # 1. Calculer la tendance de fond (Moyenne Mobile Exponentielle 200)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # Détection des Swings
    df['swing_high'] = df['high'].rolling(window=window, center=True).max()
    df['swing_low'] = df['low'].rolling(window=window, center=True).min()
    
    in_trade = False
    trade_info = {}
    
    for i in range(window, len(df)):
        current_time = df['time'].iloc[i]
        current_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        ema_200 = df['ema_200'].iloc[i]
        
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
                            in_trade = True
                            trade_info = {
                                'type': 'BUY',
                                'entry_price': ote_entry,
                                'sl': sl_level,
                                'tp': tp_level,
                                'bos': bos_level,
                                'be_triggered': False,
                                'entry_time': current_time
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
                            in_trade = True
                            trade_info = {
                                'type': 'SELL',
                                'entry_price': ote_entry,
                                'sl': sl_level,
                                'tp': tp_level,
                                'bos': bos_level,
                                'be_triggered': False,
                                'entry_time': current_time
                            }
                            
        else:
            # Gestion du trade en cours
            t_type = trade_info['type']
            entry = trade_info['entry_price']
            sl = trade_info['sl']
            tp = trade_info['tp']
            bos = trade_info['bos']
            be = trade_info['be_triggered']
            
            if t_type == 'BUY':
                # Vérifier si on doit sécuriser à Break Even (BOS)
                if not be and current_high >= bos:
                    trade_info['sl'] = entry  # SL déplacé au point d'entrée
                    trade_info['be_triggered'] = True
                    be = True
                
                # Sorties de trade
                if current_low <= trade_info['sl']:
                    # Perte ou sortie à BE
                    loss_pts = entry - trade_info['sl']
                    result = "BE" if be else "LOSS"
                    profit = 0.0 if be else -100.0 # Risque fixe de 100€
                    capital += profit
                    trades.append({**trade_info, 'exit_price': trade_info['sl'], 'exit_time': current_time, 'result': result, 'profit': profit})
                    in_trade = False
                elif current_high >= tp:
                    # Gain
                    profit = 100.0 * risk_reward
                    capital += profit
                    trades.append({**trade_info, 'exit_price': tp, 'exit_time': current_time, 'result': 'WIN', 'profit': profit})
                    in_trade = False
                    
            elif t_type == 'SELL':
                # Vérifier si on doit sécuriser à Break Even (BOS)
                if not be and current_low <= bos:
                    trade_info['sl'] = entry  # SL déplacé au point d'entrée
                    trade_info['be_triggered'] = True
                    be = True
                
                # Sorties de trade
                if current_high >= trade_info['sl']:
                    loss_pts = trade_info['sl'] - entry
                    result = "BE" if be else "LOSS"
                    profit = 0.0 if be else -100.0
                    capital += profit
                    trades.append({**trade_info, 'exit_price': trade_info['sl'], 'exit_time': current_time, 'result': result, 'profit': profit})
                    in_trade = False
                elif current_low <= tp:
                    # Gain
                    profit = 100.0 * risk_reward
                    capital += profit
                    trades.append({**trade_info, 'exit_price': tp, 'exit_time': current_time, 'result': 'WIN', 'profit': profit})
                    in_trade = False
            
            # Enregistrer la courbe de capital
            equity_curve.append(capital)
            dates.append(current_time)
            
    # S'assurer d'avoir la taille identique
    if len(equity_curve) < len(df):
        # Remplir le reste avec le dernier capital connu
        last_cap = equity_curve[-1]
        equity_curve.extend([last_cap] * (len(df) - len(equity_curve)))
        
    df['capital'] = equity_curve[:len(df)]
    return trades, df

def plot_and_save_results(df, trades, filename="backtest_real_performance.png", asset_label="Or (Gold)"):
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

    print("- Ces résultats portent sur un échantillon limité (7 jours en 1 minute) : à confirmer sur une période plus longue avant toute conclusion définitive.")
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
    américaine (par défaut 14h30-17h00, heure de l'horodatage des données)
    par rapport au reste de la journée.
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
    stratégie : téléchargement des données, analyse structurelle/technique,
    et exécution/protection des trades (avec l'historique complet des trades).
    """
    timestamp = datetime.now()
    if log_filename is None:
        log_filename = f"journal_execution_{timestamp:%Y%m%d_%H%M%S}.log"
    log_path = os.path.join(OUTPUT_DIR, log_filename)

    source_labels = {
        'yahoo_live': "Yahoo Finance (yfinance) — téléchargement en direct",
        'csv': f"Fichier CSV local ({meta.get('source_detail')})",
        'csv_fallback': f"Fichier CSV de secours ({meta.get('source_detail')}) — téléchargement en direct indisponible",
    }

    lines = []
    lines.append("=== JOURNAL D'EXÉCUTION DU BACKTEST FIBONACCI OTE ===")
    lines.append(f"Date d'exécution : {timestamp:%Y-%m-%d %H:%M:%S}")

    lines.append("\n--- 1. Téléchargement automatique en direct ---")
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
                f"#{idx:03d} {t['type']:<4} | entrée {t['entry_time']} @ {t['entry_price']:.2f} "
                f"| SL {t['sl']:.2f} | TP {t['tp']:.2f} | BOS {t['bos']:.2f} | BE déclenché : {be_str} "
                f"| sortie {t['exit_time']} @ {t['exit_price']:.2f} | résultat {t['result']} | P&L {t['profit']:+.2f} €"
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

def compare_assets_performance(results, filename="comparatif_actifs.png", log_filename="comparatif_actifs.log"):
    """
    Compare scientifiquement les performances de la stratégie sur plusieurs actifs
    (Or, Nasdaq, EUR/USD...) : tableau récapitulatif, graphique comparatif des
    indicateurs clés et journal texte.
    """
    valid_results = [r for r in results if r.get('stats', {}).get('total', 0) > 0]
    if not valid_results:
        print("\nAucun résultat exploitable pour la comparaison inter-actifs (aucun trade sur aucun actif).")
        return None

    labels = [r['label'] for r in valid_results]
    net_profits = [r['stats']['net_profit'] for r in valid_results]
    win_rates = [r['stats']['win_rate'] for r in valid_results]
    profit_factors = [min(r['stats']['profit_factor'], 5.0) for r in valid_results]  # plafonné pour l'affichage
    drawdowns = [r['stats']['max_drawdown'] for r in valid_results]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    colors = ["#cc5500", "#1f77b4", "#2ca02c", "#9467bd"][:len(labels)]

    axes[0, 0].bar(labels, net_profits, color=colors)
    axes[0, 0].set_title("Profit net (€)")
    axes[0, 0].axhline(0, color="black", linewidth=0.8)

    axes[0, 1].bar(labels, win_rates, color=colors)
    axes[0, 1].set_title("Win rate (%)")

    axes[1, 0].bar(labels, profit_factors, color=colors)
    axes[1, 0].set_title("Profit factor (plafonné à 5.0)")

    axes[1, 1].bar(labels, drawdowns, color=colors)
    axes[1, 1].set_title("Drawdown maximum (%)")

    for ax in axes.flat:
        ax.grid(True, axis='y', linestyle="--", alpha=0.5)
        ax.tick_params(axis='x', rotation=15)

    fig.suptitle("Comparatif de la stratégie Fibonacci OTE selon l'actif", fontsize=14, fontweight='bold')
    plt.tight_layout()
    output_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\nGraphique comparatif sauvegardé sous : {output_path}")

    # Tableau texte + journal
    header = f"{'Actif':<15}{'Trades':>8}{'Win rate':>10}{'Profit factor':>15}{'Drawdown max':>15}{'Profit net':>14}"
    lines = ["=== COMPARATIF DES PERFORMANCES PAR ACTIF ===", "", header, "-" * len(header)]
    for r in valid_results:
        s = r['stats']
        lines.append(
            f"{r['label']:<15}{s['total']:>8}{s['win_rate']:>9.1f}%{s['profit_factor']:>15.2f}"
            f"{s['max_drawdown']:>14.2f}%{s['net_profit']:>13.2f} €"
        )
    print("\n" + "\n".join(lines))

    best = max(valid_results, key=lambda r: r['stats']['net_profit'])
    lines.append("")
    lines.append(f"Actif le plus performant (profit net) : {best['label']} ({best['stats']['net_profit']:+.2f} €)")
    print(f"\n- Actif le plus performant (profit net) : {best['label']} ({best['stats']['net_profit']:+.2f} €)")

    log_path = os.path.join(OUTPUT_DIR, log_filename)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Journal comparatif sauvegardé sous : {log_path}")

    return {'labels': labels, 'net_profits': net_profits, 'win_rates': win_rates,
            'profit_factors': profit_factors, 'drawdowns': drawdowns, 'best': best['label']}

if __name__ == "__main__":
    # Configuration des actifs à comparer : Or (référence), Nasdaq et EUR/USD.
    # Yahoo Finance limite l'historique en 1 minute aux 7 derniers jours.
    ASSETS = [
        {'label': 'Or (Gold)', 'ticker': 'GC=F', 'period': '7d', 'interval': '1m',
         'csv_fallback': 'mock_gold_data.csv'},
        {'label': 'Nasdaq', 'ticker': 'NQ=F', 'period': '7d', 'interval': '1m',
         'csv_fallback': 'mock_nasdaq_data.csv'},
        {'label': 'EUR/USD', 'ticker': 'EURUSD=X', 'period': '7d', 'interval': '1m',
         'csv_fallback': 'mock_eurusd_data.csv'},
        {'label': 'Pétrole (WTI)', 'ticker': 'CL=F', 'period': '7d', 'interval': '1m',
         'csv_fallback': 'mock_oil_data.csv'},
    ]
    window = 20
    results = []
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for asset in ASSETS:
        slug = asset['label'].lower().replace('/', '').replace(' ', '_').replace('(', '').replace(')', '')
        print(f"\n{'=' * 20} BACKTEST : {asset['label']} ({asset['ticker']}) {'=' * 20}")
        try:
            csv_fallback = os.path.join(OUTPUT_DIR, asset['csv_fallback'])
            data, meta = download_or_load_data(
                ticker=asset['ticker'], period=asset['period'], interval=asset['interval'],
                csv_path=csv_fallback if os.path.exists(csv_fallback) else None
            )
            meta['n_candles'] = len(data)
            meta['window'] = window
            trades, df_result = run_fibonacci_backtest(data, window=window)
            plot_and_save_results(df_result, trades, filename=f"backtest_{slug}_performance_{run_timestamp}.png", asset_label=asset['label'])
            stats = analyze_performance(df_result, trades)
            session_analysis = analyze_session_performance(trades)
            generate_execution_log(meta, trades, stats, session_analysis=session_analysis,
                                    log_filename=f"journal_execution_{slug}_{run_timestamp}.log")
            results.append({'label': asset['label'], 'stats': stats})
            print(f"Backtest {asset['label']} complété avec succès !")
        except Exception as e:
            print(f"Erreur lors de l'exécution du backtest pour {asset['label']} : {e}")
            results.append({'label': asset['label'], 'stats': {'total': 0}})

    compare_assets_performance(results, filename=f"comparatif_actifs_{run_timestamp}.png",
                                log_filename=f"comparatif_actifs_{run_timestamp}.log")
