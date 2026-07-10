# Centralized Configuration
# Changed from "gemini-3-pro-preview" (resolves to gemini-3.1-pro internally,
# free-tier limit=0 on this key) to "gemini-2.0-flash" — the model the
# ProviderToggle UI labels it as, confirmed present in the model list for this
# API key via ListModels. If the free-tier quota for this key is fully
# exhausted, switch to Groq in the frontend ProviderToggle instead.
GEMINI_MODEL = "gemini-2.0-flash"
