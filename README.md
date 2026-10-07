# dati-mercato

Ogni mattina (lun-ven) scarica da Yahoo Finance (tramite yfinance) i prezzi della watchlist, calcola gli indicatori tecnici e pubblica `data/latest.csv` / `data/latest.json` su GitHub. La skill **analista-titoli** legge questo file invece di stimare SMA200, volatilità e forza relativa.

## Setup sul mini PC Windows (una volta sola)

1. **Crea il repository** su GitHub: nome `dati-mercato`, **pubblico** (contiene solo prezzi di mercato, nessun dato personale). Pubblico serve perché Claude lo legga senza token.
2. **Clona e copia i file** (PowerShell):
   ```powershell
   cd C:\Trading\GitHub
   git clone https://github.com/Belleo/dati-mercato.git
   cd C:\Trading\GitHub\dati-mercato
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. **Primo test e primo push** (la prima volta Git Credential Manager chiede il login GitHub e lo memorizza):
   ```powershell
   .venv\Scripts\python market_data.py --push
   ```
   Verifica che su GitHub compaia `data/latest.csv`.
4. **Pianifica l'esecuzione mattutina** (PowerShell):
   ```powershell
   $action   = New-ScheduledTaskAction -Execute "C:\Trading\GitHub\dati-mercato\run_daily.bat"
   $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:00
   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) -ExecutionTimeLimit (New-TimeSpan -Hours 1)
   Register-ScheduledTask -TaskName "DatiMercato" -Action $action -Trigger $trigger -Settings $settings -Force
   ```
   - Lun-ven alle 09:00: il lunedì registra la chiusura del venerdì, il martedì quella del lunedì, ecc.
   - **Recupero**: se alle 09:00 il PC è spento, l'attività parte appena il PC viene acceso e l'utente accede (`-StartWhenAvailable`), solo con la rete disponibile.
   - Se lo scarico o il push falliscono, riprova fino a 3 volte ogni 10 minuti.
   - Se il recupero avviene a mercati aperti, `prezzo` è un valore intraday: viene sostituito dalla chiusura alla successiva esecuzione.
   - Facoltativo, in *Utilità di pianificazione → DatiMercato → Proprietà*: "Esegui indipendentemente dalla connessione dell'utente" (chiede la password di Windows) e, in *Condizioni*, "Riattiva il computer per eseguire l'attività" se il PC va in sospensione.

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
- **Errore `CertificateVerifyError` / "unable to get local issuer certificate"**: un antivirus (es. Avast Web Shield) ispeziona l'HTTPS. Lo script lo gestisce da solo (`use_windows_certs()`: unisce certifi e i certificati di Windows in `cacert.pem`).
- **Push fallito**: controlla `log.txt`; rifai un push manuale per rinnovare le credenziali.
