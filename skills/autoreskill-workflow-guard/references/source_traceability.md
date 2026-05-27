# Source Traceability

Portable AutoResearch maps OpenClaw concepts into `.autoreskill/` contracts without depending on the OpenClaw runtime.

| Portable contract | OpenClaw source concept | Runtime dependency removed |
| --- | --- | --- |
| `goal_state.json` | workflow control / auto iterator state | `.openclaw-research/`, `PROJECT_MANIFEST.json` |
| `GRAPH_BUILD_DECISION.json` | graph build direct authority | OpenClaw graph resolver service |
| `IDEA_CATALYST_CONTRACT.json` | Researcher idea catalyst completion | OpenClaw researcher workspace |
| `INNOVATION_PACKET.json` | Orchestrator experiment-plan authority | OpenClaw workflow-stage completion resolver |
| `EXPERIMENT_REVIEW_PACKET.json` | reviewed-auto prelaunch gate | OpenClaw planner launch gate |
| `EXPERIMENT_MANIFEST.json` + dry-run log | Coder implementation contract | OpenClaw runtime queue |
| `CLAIM_EVIDENCE_MATRIX.md` | Analyzer claim-evidence gate | OpenClaw analyzer handoff |
| `REVIEW_FINDINGS.json` | Reviewer pressure gate | OpenClaw review stage |

This file is a traceability note, not a runtime import. The skill pack must remain usable when the OpenClaw repository is absent.
