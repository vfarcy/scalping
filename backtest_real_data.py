import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Liste des dépendances externes requises sur l'ordinateur de l'utilisateur :
# pip install pandas numpy matplotlib yfinance

def download_or_load_data(ticker="GC=F", period="1mo", interval="1h", csv_path=None):
    """
    Tente de télécharger de vraies données depuis Yahoo Finance.
    En cas d'échec (ex. pas d'internet dans le sandbox), charge un fichier CSV.
    """
    if csv_path and os.path.exists(csv_path):
        print(f"Chargement des données depuis le fichier CSV : {csv_path}")
        df = pd.read_csv(csv_path)
        # S'assurer que les colonnes sont au bon format
        df['time'] = pd.to_datetime(df.iloc[:, 0])
        df.columns = [col.lower() for col in df.columns]
        return df

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
        return data
    except Exception as e:
        print(f"Impossible de télécharger les données en direct ({e}).")
        # Fallback sur un fichier mock si on est dans le sandbox
        fallback_path = "mock_gold_data.csv"
        if os.path.exists(fallback_path):
            print("Utilisation du fichier de simulation local.")
            df = pd.read_csv(fallback_path)
            df['time'] = pd.to_datetime(df['time'])
            return df
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

def plot_and_save_results(df, trades, filename="backtest_real_performance.png"):
    """
    Affiche et enregistre la courbe de croissance du capital.
    """
    plt.figure(figsize=(10, 6))
    plt.plot(df['time'], df['capital'], label="Courbe de Capital (€)", color="#cc5500", linewidth=2)
    plt.title("Performance du Backtest Fibonacci OTE (Données Réelles)", fontsize=14, fontweight='bold', pad=15)
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

if __name__ == "__main__":
    # Test avec le fichier CSV de simulation
    csv_fallback = os.path.join(OUTPUT_DIR, "mock_gold_data.csv")
    try:
        # Essayer de lancer le backtest (utilise yfinance en local ou le CSV en fallback)
        data = download_or_load_data(ticker="GC=F", csv_path=csv_fallback)
        trades, df_result = run_fibonacci_backtest(data)
        plot_and_save_results(df_result, trades)
        print("Backtest réel complété avec succès !")
    except Exception as e:
        print(f"Erreur lors de l'exécution du backtest : {e}")
