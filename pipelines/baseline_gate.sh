# Sourced by Actions bash steps; recursive make runs normally inside the wrapper.
make() {
  python3 -m pipelines.baseline_reds --context "${BASELINE_RED_CONTEXT:-CI}" -- make "$@"
}
