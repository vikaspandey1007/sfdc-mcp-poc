"""Gate 4 hosted runtime -- the production-shaped entry point deployed to
Render (server/app.py), plus the hosted OAuth callback routes
(server/oauth.py). Not used for local development, which keeps using
`adk web` and `python -m auth.token_broker` directly.
"""
