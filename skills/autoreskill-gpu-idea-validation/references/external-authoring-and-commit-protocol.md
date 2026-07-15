# External Campaign Authoring And Commit Protocol

This protocol covers only the offline `external_material` route. It performs no
retrieval, GPU allocation, remote execution, or job submission.

Commands are CWD-independent when these absolute variables are set:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/autoreskill-gpu-idea-validation"
PROJECT_ROOT=/absolute/path/to/project
```

## Authoring commands

Print a draft campaign shape:

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" template \
  --kind campaign \
  --direction "<research direction>"
```

The printed object is an authoring scaffold, not a passed campaign. Before it
can be seeded it must contain three evidence lanes, citable verified method
lineage, explicit structural gaps, 8-12 complete candidates, a 3-5 candidate
shortlist, and 1-4 admitted candidates. Protected commitments must be
recomputed after every protected field change.

CAS-write a complete campaign from strict finite JSON:

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" seed \
  --project "$PROJECT_ROOT" \
  --input /absolute/path/to/complete-campaign.json \
  --expected-current-campaign-sha256 <sha256-or-absent>
```

`seed` validates before writing. When a gate already exists, `campaign_id` is
immutable and a changed campaign must increment `campaign_revision` by exactly
one and set `parent_campaign_sha256` to the committed campaign hash.

## Commit layout

`materialize` takes the project lock before rereading the gate and campaign.
Invoke it with the gate hash observed immediately before the action (`absent`
only when no gate exists):

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" materialize \
  --project "$PROJECT_ROOT" \
  --expected-current-gate-sha256 <sha256-or-absent>
python3 "$SKILL_DIR/scripts/idea_campaign.py" verify-gate \
  --project "$PROJECT_ROOT"
```

It writes immutable artifacts first:

- `ideation/committed/INNOVATION_SLOT_MAP.<sha256>.json`
- `ideation/committed/NON_PAPERNEXUS_IDEA_LINT.<sha256>.json`

It then rechecks the campaign and gate hashes and writes
`ideation/PRE_IDEA_EVIDENCE_GATE.json` last. The gate's `lint_ref`,
`innovation_slot_map_path`, and `slot_map_ref` identify these immutable files.
Consumers must resolve those gate refs under `.autoreskill`; fixed canonical
lint or slot paths are not commit authority.

`verify-gate` is read-only and revalidates the current campaign plus the exact
content-addressed lint/slot lineage. Run it after materialization and before
authoring a downstream external pool or scorecard.

## Independent panel writer

Start from `PANEL_DESIGN_REVIEW.template.json`, bind it to the current campaign
hash, and list only admitted external candidate ids. The generation and review
contexts must both be non-empty and different, and `reviewer_role` must be
`independent_panel`.

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" write-panel-design-review \
  --project "$PROJECT_ROOT" \
  --input /absolute/path/to/panel-review.json \
  --expected-current-panel-sha256 <sha256-or-absent>
```

The writer requires a valid passed content-addressed external gate and uses a
CAS update. `status="passed"` requires `verdict="advance"`; a blocked review
cannot advance.
