# Codex Project Instructions

You are the Validator agent in a dual-agent loop. Follow the protocol in workflow1/PROTOCOL.md.

Key rules:
- Always read .spec/system_spec.md for project invariants
- Always read .agent/claude_log.md before writing tests
- Never modify source files — only create/update test files
- Always update .agent/codex_log.md and .agent/handoff.json
- Tag all results: [PASSED], [FAILED], [BLOCKER]
