# RSS Full Text Service

Un servizio web gratuito che genera feed RSS con testo completo a partire da feed parziali (solo titoli e link).

## Come funziona

Il servizio riceve l'URL di un feed RSS parziale, visita ogni articolo, ne estrae il testo completo e restituisce un nuovo feed RSS con il contenuto intero. I risultati vengono salvati in cache per 30 minuti per ridurre il numero di richieste ai siti sorgente.

```
https://tuo-servizio.onrender.com/feed?url=https://esempio.com/feed.rss
```

## Stack

- **Python** + **Flask** — server web
- **feedparser** — parsing del feed RSS originale
- **httpx** — fetch degli articoli
- **trafilatura** — estrazione del testo principale dalla pagina
- **cachetools** — cache in memoria (TTL 30 minuti)
- **gunicorn** — server WSGI per la produzione

## Deploy su Render.com (gratuito)

### Prerequisiti

- Account [GitHub](https://github.com)
- Account [Render.com](https://render.com) (registrazione gratuita)

### Istruzioni

1. Fai il fork o clona questo repository sul tuo account GitHub
2. Vai su [render.com](https://render.com) → **New +** → **Web Service**
3. Connetti il tuo account GitHub e seleziona questo repository
4. Configura il servizio con questi parametri:

   | Campo | Valore |
   |---|---|
   | Region | Frankfurt (EU) |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn app:app` |
   | Plan | Free |

5. Clicca **Create Web Service** e aspetta 2-3 minuti

Il servizio sarà disponibile su un URL tipo `https://rss-fulltext-xxxx.onrender.com`.

## Utilizzo

### Endpoint

```
GET /feed?url=<URL_DEL_FEED>
```

### Esempio

```
https://tuo-servizio.onrender.com/feed?url=https://www.example.com/rss.xml
```

Incolla questo URL nel tuo feed reader (Reeder, NetNewsWire, Feedly, ecc.) al posto dell'URL originale.

## Note sul piano gratuito

Il servizio gratuito di Render va in **sleep dopo 15 minuti di inattività**. La prima richiesta dopo lo sleep impiega circa 30 secondi per rispondere.

Per tenerlo sempre attivo, puoi usare [cron-job.org](https://cron-job.org) (gratuito) per fare un ping all'URL del servizio ogni 10 minuti.

## Struttura del progetto

```
├── app.py              # Applicazione principale Flask
├── requirements.txt    # Dipendenze Python
├── render.yaml         # Configurazione Render.com
└── README.md
```

## Limitazioni

- Vengono processati al massimo 20 articoli per feed
- Alcuni siti bloccano il fetch automatico tramite bot detection
- Se un articolo non è accessibile, viene mantenuto il contenuto originale del feed

## Licenza

MIT
