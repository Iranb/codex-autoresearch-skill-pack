# Codex AutoResearch Skill Pack

Private Codex skill pack for portable AutoResearch workflows aligned with OpenClaw research-control conventions.

## Contents

- `skills/autoreskill-*`: AutoResearch workflow, PaperNexus, planning, experiment, writing, review, and memory skills.
- `skills/academic-paper-reviewer`: reviewer workflow and `REVIEW_FINDINGS.json` adapter support.
- `docs/execplans`: implementation ExecPlan documents for contract hardening and OpenClaw alignment gaps.

## Sensitive Information Policy

This repository is intended to contain skill instructions, scripts, schemas, and planning documents only.
Do not commit live workflow states, API tokens, PaperNexus credentials, run logs with secrets, model keys, SSH keys, or private local project data.

The uploaded copy has been sanitized to remove user-specific absolute paths and private PaperNexus endpoint addresses. Configure local paths and remote endpoints through environment variables or command-line arguments, for example:

```bash
export CODEX_SKILL_ROOT="$HOME/.codex/skills"
export PAPERNEXUS_REMOTE_MCP_URL="https://your-papernexus-remote.example/mcp"
export PAPERNEXUS_REMOTE_API_TOKEN="<token-from-your-secret-store>"
```

## Install Locally

To use these skills in Codex, copy the desired skill directories under your Codex skill root:

```bash
rsync -a skills/autoreskill-* "$HOME/.codex/skills/"
rsync -a skills/academic-paper-reviewer "$HOME/.codex/skills/"
```

Then start a new Codex session so the skill registry refreshes.

## Validation

The Python scripts are intentionally dependency-light. A basic local syntax check is:

```bash
python -m py_compile skills/*/scripts/*.py
```

Workflow validation for a concrete project should be run from a local Codex environment with PaperNexus configured:

```bash
python skills/autoreskill-workflow-guard/scripts/goal_validate.py \
  --project /path/to/autoresearch-project \
  --skill-root "$PWD/skills"
```
