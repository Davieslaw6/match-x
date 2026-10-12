# Providers and LLM setup
football-data.org: free tier, token in `FOOTBALL_DATA_TOKEN`. Coverage, rate limits and licence terms were NOT verified live; check the provider's current terms before use. UNVERIFIED.
football-data.co.uk CSVs: used for historical results and closing odds; check the site's terms of use. Kickoffs are UK local time and converted to UTC.
LLM: `LLM_PROVIDER=mock` (rule-based demo) or `openai_compatible` with LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (adapter UNVERIFIED live). Keys stay server-side.
Vision extraction for screenshots: no real extractor is built; only a test double exists.
Bookmakers: only the manual integration exists. A real integration needs authorised access and must follow the bookmaker's terms. Never scrape or collect passwords.
