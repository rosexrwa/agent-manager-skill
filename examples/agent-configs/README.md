# Agent Configuration Scenarios

This folder contains ready-to-adapt YAML templates for common `agent-manager` use cases.

## Included Scenarios

- `grok-cli-agent.yaml`: xAI Grok Build CLI (`launcher: grok`) in managed tmux
- `code-review-agent.yaml`: Automated pull request review and risk triage
- `documentation-generator-agent.yaml`: Nightly docs refresh and weekly doc audit
- `test-runner-agent.yaml`: Smoke tests + nightly regression with heartbeat checks
- `deployment-assistant-agent.yaml`: Release readiness and rollout support
- `monitoring-alert-agent.yaml`: SLO/error-budget alert triage and on-call support
- `data-analysis-agent.yaml`: Log/KPI analysis and weekly insights reporting

## How To Use

1. Pick one template and customize `name`, `skills`, `task`/`task_file`, and cron values.
2. Copy the YAML into an agent frontmatter block under `agents/EMP_XXXX.md`.
3. Keep your role instructions below the frontmatter.
4. Validate and run with `agent-manager`.

Example:

```markdown
---
name: pr-reviewer
description: Pull request code review specialist
working_directory: ${REPO_ROOT}
launcher: codex
launcher_args:
  - --model=gpt-5.3-codex
skills:
  - review-pr
schedules:
  - name: morning-triage
    cron: "0 9 * * 1-5"
    task: |
      Review new pull requests and report high-risk changes.
---

# PR Reviewer Agent

You are responsible for code review quality...
```

## Validate Configuration

```bash
# From your workspace root
CLI="python3 .agent/skills/agent-manager/scripts/main.py"

$CLI doctor
$CLI list
$CLI schedule list
$CLI heartbeat list
```

## Notes

- `schedules` can contain many jobs per agent.
- `heartbeat` supports one periodic check-in policy per agent.
- Use `${REPO_ROOT}` in paths to keep configs portable.
