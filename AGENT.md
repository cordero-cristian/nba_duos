# Agent Handoff Notes

## Project purpose
Streamlit app that visualizes NBA 2-player lineup (duo) impact using `nba_api`.

## What was optimized
- Initial request path now uses explicit request timeout + retry with exponential backoff.
- Data fetch is still cached for 1 hour via `st.cache_data`.

## Local run process
1. Install dependencies:
   ```bash
   uv sync
   ```
2. Start Streamlit:
   ```bash
   uv run streamlit run main.py --server.headless true --server.port 8501
   ```
3. Open browser at:
   - `http://localhost:8501`

## Recommended debugging flow for request timeouts
- Verify outbound connectivity to NBA stats endpoint.
- Temporarily reduce filters and confirm dataframe shape after fetch.
- If API is flaky, increase `REQUEST_RETRIES` and/or `REQUEST_TIMEOUT_SECONDS` in `main.py`.

## Quick checks
```bash
uv run python -m py_compile main.py
uv run python -c "import main; print('import_ok')"
```

## Notes for next agent
- The first load calls NBA stats once and can still be slow if the upstream API is degraded.
- Cached data helps all subsequent app reruns within TTL.
