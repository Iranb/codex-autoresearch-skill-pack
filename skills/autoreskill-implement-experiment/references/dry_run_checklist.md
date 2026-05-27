# Dry-run Checklist

- Imports succeed.
- Dataset path handling does not mutate source data.
- Baseline and proposed configs load.
- One tiny batch trains/evaluates.
- Metrics are emitted in parseable JSON/CSV.
- Logs are persisted.
- No protocol drift from review packet.
