# Centralized Configuration
# Changed from "gemini-3-pro-preview" (resolves to gemini-3.1-pro internally,
# free-tier limit=0 on this key) to "gemini-2.0-flash" — the model the
# ProviderToggle UI labels it as, confirmed present in the model list for this
# API key via ListModels. If the free-tier quota for this key is fully
# exhausted, switch to Groq in the frontend ProviderToggle instead.
GEMINI_MODEL = "gemini-2.5-flash"

# Operational Provider Defaults
PROVIDER_MAX_WAIT = {
    "groq": 60,
    "gemini": 30,
    "openai": 120,
    "anthropic": 60,
    "tavily": 60,
}
PROVIDER_SEMAPHORE_LIMIT = 12
PROVIDER_COOLDOWN_DURATION = 10.0
PROVIDER_RETRY_COUNT = 5
PROVIDER_RETRY_DELAY = 5
PROVIDER_BACKOFF_MULTIPLIER = 2.0
PROVIDER_JITTER_RANGE = 0.1
