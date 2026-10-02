"""VORP translation for as-published sources.

Jeremy 2026-10-01: Instead of statistical rescaling (quantile mapping, z-scores),
translate publisher values through VORP methodology:
1. Infer the publisher's implicit replacement level from their value curve
2. Extract "value over their replacement"
3. Rebuild through OUR VORP framework (our starter/bench/position assumptions)

Fluid: re-infer every bake, nothing hardcoded. Supabase-backed.
"""
