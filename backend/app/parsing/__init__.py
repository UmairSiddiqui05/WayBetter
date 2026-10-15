"""Natural-language trip parsing (POST /trip/ai-parse, F-08).

A parser (LLMProvider: a local model, or the deterministic rules fallback) only fills
`ParsedTrip` — words, not coordinates, prices or routes (D-11). Everything after that —
matching places, dates, defaults, what is missing — is ordinary server code here.
"""
