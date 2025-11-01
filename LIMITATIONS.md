# Limitations

- OHLCV-only: no order books, news, or alt data beyond optional sentiment in UI project.
- Regime changes: models trained on historical regimes may underperform during structural breaks.
- Network dependencies: ccxt public endpoints may rate-limit or be temporarily unavailable (retries added).
- No persistence: container filesystem may be ephemeral (plots saved per run but not durable).

