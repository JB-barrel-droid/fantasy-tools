# JEG-238: conserve group totals at producer precision

The Option C producer rounds its factor to6 decimal places and each imputed value
to2 places. Equal native1/1/1 with target20 produces6.67/6.67/6.67 (sum20.01).
It also emits a factor that cannot reproduce those emitted values and turns
small positive surplus into0 before reweighting.

The producer now emits the computed factor and value at full floating precision.
No allocation, reference, roster, cut handling, fixture or rendered behavior is
changed. Presentation can round separately; computational artifacts must not.
This is stacked on JEG237/PR47's input-validation slice.

```bash
python3 -m unittest tests.test_imputed_vorps_precision tests.test_imputed_vorps_validation -v
git diff --check
```

12 tests pass (4 precision +8 input). Precision cases independently verify thirds
conservation/factor reproduction, tiny-positive/native ratios/zero, all8group
target sums and full-precision CLI JSON roundtrip. The old rounded JEG237 producer
fails the thirds regression as required. Numeric checks use floating tolerances;
synthetic arithmetic identifiers do not certify canonical source coverage.
Makefile includes both modules. Full composite validation and review details are
recorded in PR/Linear; Roman's independent integration review remains required.
No full Sheet/source/config/rendered/production approval is implied; JEG183 and
JEG239–243 remain open.
