#!/usr/bin/env bash
# Wrapper so `claude mcp add` (no --cwd flag) can launch beem_agent.server
# with the right working directory for `python -m` package resolution.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m beem_agent.server
