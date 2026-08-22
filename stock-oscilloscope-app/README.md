# Signal Corps Market Scope

The oscilloscope displays a synthetic historical trace and appends a current
Finnhub quote every 30 seconds. The status strip always identifies whether the
latest value is live, cached, or demo data.

## Run locally

1. Create a free Finnhub API key at https://finnhub.io/
2. From this directory, create a virtual environment and install Flask:

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. Put the key in the server process environment and start the app:

   ```sh
   export FINNHUB_API_KEY="your-key-here"
   python server.py
   ```

4. Open http://127.0.0.1:4173/

Do not put the API key in `app.js`, a URL, or a committed configuration file.

## Endpoints

- `GET /api/health` reports server readiness without revealing the key.
- `GET /api/quote/AAPL` returns a normalized quote.
- Quote responses are cached for 30 seconds to avoid needless provider calls.
- If Finnhub is temporarily unavailable, the server returns the last cached
  quote marked `stale`; otherwise the browser visibly falls back to demo data.

## Data note

The long trace is still synthetic history. Only values appended after the page
starts are live quotes. This keeps the first version fast and inexpensive while
making the data provenance explicit. A later version can replace the seed trace
with historical candles from a provider plan that permits them.
