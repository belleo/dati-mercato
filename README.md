# dati-mercato

Ogni sera scarica da Yahoo Finance (tramite yfinance) i prezzi della watchlist, calcola gli indicatori tecnici e pubblica `data/latest.csv` / `data/latest.json` su GitHub. La skill **analista-titoli** legge questo file invece di stimare SMA200, volatilità e forza relativa.

## Setup sul mini PC Windows (una volta sola)

1. **Crea il repository** su GitHub: nome `dati-mercato`, **pubblico** (contiene solo prezzi di mercato, nessun dato personale). Pubblico serve perché Claude lo legga senza token.
2. **Clona e copia i file** (PowerShell):
   ```powershell
   cd C:\
   git clone https://github.com/Belleo/dati-mercato.git
   # copia dentro C:\dati-mercato i file di questo pacchetto
   cd C:\dati-mercato
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. **Primo test e primo push** (la prima volta Git Credential Manager chiede il login GitHub e lo memorizza):
   ```powershell
   .venv\Scripts\python market_data.py --push
   ```
   Verifica che su GitHub compaia `data/latest.csv`.
4. **Pianifica l'esecuzione serale**:
   ```powershell
   schtasks /Create /TN "DatiMercato" /TR "C:\dati-mercato\run_daily.bat" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 22:45 /F
   ```
   22:45 = dopo la chiusura di Wall Street (22:00 ora italiana). In *Utilità di pianificazione → DatiMercato → Proprietà* spunta "Esegui anche se l'utente non è connesso" e, in *Condizioni*, "Riattiva il computer per eseguire l'attività" se il PC va in sospensione.

## Modificare la watchlist

Modifica `watchlist.csv` (colonne `ticker,nome,mercato`; mercato = `IT` o `US`). Ticker Yahoo: Borsa Italiana con suffisso `.MI` (es. `LDO.MI`), USA senza suffisso. Poi `git add watchlist.csv && git commit -m "watchlist" && git push`.

## Campi calcolati

| Campo | Significato |
|---|---|
| prezzo, data_prezzo | Ultima chiusura (rettificata) e sua data |
| sma50, sma200, dist_sma200 | Medie mobili e distanza % dalla SMA200 |
| sopra_sma200, sma200_in_salita, golden_cross | Filtri di trend (SMA200 vs 20 sedute fa; SMA50 > SMA200) |
| rsi14 | RSI a 14 giorni |
| ret_1m/3m/6m/12m, ret_ytd | Rendimenti |
| forza_rel_6m/12m | Rendimento relativo vs FTSE MIB (IT) o S&P 500 (US) |
| max_52s, min_52s, dist_max_52s, dist_min_52s | Range 52 settimane |
| vol_1a, max_drawdown_1a | Volatilità annualizzata e massimo drawdown a 1 anno |

Valori percentuali in decimali (0.05 = +5%). Con `--fundamentals` aggiunge capitalizzazione, P/E, EV/EBITDA, dividend yield, beta (più lento, a volte limitato da Yahoo).

## Problemi comuni

- **Nessun dato**: yfinance è non ufficiale; aggiorna con `.venv\Scripts\pip install -U yfinance`.
- **Push fallito**: controlla `log.txt`; rifai un push manuale per rinnovare le credenziali.
