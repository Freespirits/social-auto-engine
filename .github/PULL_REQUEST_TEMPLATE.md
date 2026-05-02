## What this changes

<!-- One paragraph. The user-facing impact, not the implementation detail. -->

## Why

<!-- Link the issue: Closes #XX -->

## Approval-queue safety check

<!-- Required for any PR that adds a write action -->

- [ ] This change does not add a new write action, OR
- [ ] The new write action goes through the approval queue, OR
- [ ] The new write action is opt-in with a visible warning banner

## Verification

<!-- How did you confirm this works? -->

- [ ] Ran the dashboard locally (`python -m dashboard.app`)
- [ ] Smoke-tested the MCP server (`python server.py`)
- [ ] Tested against a real account (describe below)

## Screenshots / recording

<!-- For any UI change. -->
