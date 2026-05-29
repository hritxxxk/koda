# Koda

Minimal setup for DSA/SQL practice.

## Setup

1. Install the package (deps + CLI script):
   ```bash
   pip install -e .
   ```
2. Configure AI provider (optional — default is Ollama, no key needed):
   ```bash
   cp .env.example .env
   # Then edit .env to set AI_PROVIDER and API key for your chosen provider
   ```
3. Run the app:
   ```bash
   koda start
   ```
   If `koda` isn't on your PATH, use:
   ```bash
   python -m src.ai_dsa.cli start
   ```


