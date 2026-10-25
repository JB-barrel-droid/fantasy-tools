## 2026-10-23 - JEG-969 step 3: promotion/demotion model implementation

Ticket: JEG-969 lane A. Branch: research/JEG-969-bench-share.

### What changed

Implemented promotion/demotion model behind `promotion_model` flag (off by
default) in all three engines:
- Python reference (`pipelines/value_reference.py`): new functions
  `load_promotion_config`, `_promotion_rate`, `_demotion_rate`,
  `_apply_promotion_model`; threaded through `_source_lines`, `run_pipeline`,
  `Setting`, and `compute`.
- JS engine (`app/trade-value-chart/assets/value-model.js`): embedded
  `PROMOTION_RATES`, `DEMOTION_RATES`, `esApplyPromotionModel`; hooked after
  `esPositionParts` when `setting.promotion_model` is truthy.
- Spec reference (`pipelines/spec_reference/value_pipeline.py`):
  `apply_promotion_model`; threaded through `price_source`, `run_week`, `run`.

Config: `config/promotion_rates.json` (measured rates from step 2).

### Verified (check named)

- `python3 -m pytest tests/test_value_pipeline_engine.py` — 18/18 passed
  (14 existing + 4 new promotion model tests + 1 spec parity)
- `python3 -m pytest tests/test_spec_reference_value_pipeline.py` — 23/23 passed
- `python3 -m pytest tests/test_value_check.py` — 21/21 passed
- `value_check compare --rerun-engine --strict` — agree, 1,224,183 values
- New tests prove:
  - Flag ON changes lineup shares and bench share readout (differs from OFF)
  - Spec reference and JS engine agree on bench share with flag ON
  - 10x broken rate is caught (negative test)
  - Flag OFF preserves existing values (no regression)

### Claimed (not confirmed)

- Python reference and JS engine agree exactly to 1e-6 with flag ON (tested
  spec vs JS to 1e-4, not Python ref vs JS directly — would need Inputs
  plumbing for the worked example fixture).
