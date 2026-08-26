# 🧠 Dev Brain Agent Schema & Operating Protocol (Universal)

This repository serves as an **Engineering Second Brain & Developer Knowledge Base**.
For the full operating manual, schema definitions, and workflows, refer to [`GEMINI.md`](GEMINI.md).

---

## 🤖 Core Protocols for AI Agents (Antigravity, Cursor, Claude Code, Windsurf, Codex):

1. **AI-Maintained Knowledge**: When user provides code, error traces, or architecture patterns, synthesize and store them in `wiki/`.
2. **Graph-First Retrieval**: Before answering complex architecture questions or fixing bugs, search `dev-brain/wiki/` via `python scripts/search_wiki.py "<query>" --traverse`.
3. **Continuous Syncing & Ingest**: When user commands "ซิ้ง", "sync", "ingest", "scan", or "นำเข้า", execute `python scripts/sync_projects.py .` (or pass `--name "<CustomAlias>"` if the user specified a custom name) to scan the current workspace, generate Obsidian Wiki & Canvas, and register the project into `repositories.md`.


4. **Playbook Learning**: When user commands "จำ" or after solving tricky bugs, document root cause and fix in `wiki/playbooks/` and re-index via `python scripts/run_graphify.py`.
5. **Zero-Dependency Runtime**: All scripts run on pure Python Standard Library (no `pip install` required).

