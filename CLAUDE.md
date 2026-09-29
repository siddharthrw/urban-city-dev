# City Planning OS — Claude guidance

## Who you're helping

There are two people on this project:

- **Siddharth (owner)** — full access to everything
- **Collaborator** — non-technical; may only add data and documentation

**Read this file before doing anything.** If you are unsure which person you are assisting, ask them to identify themselves.

---

## If you are assisting the COLLABORATOR

### You MAY touch
- `docs/` — guides, notes, research
- `data/` — raw data files (CSV, Excel, GeoParquet, Shapefile, PDF)
- `rules/` — planning rule YAML/JSON config
- `*.md` files at the project root (except this one)

### You MUST NOT touch
- `frontend/` — React/TypeScript source code
- `backend/` — Python/FastAPI source code
- `pyproject.toml`, `*.config.*`, `package.json`, `package-lock.json`
- `.github/` — CI and repo configuration
- `.env`, `.env.example`, or any file containing secrets
- `CLAUDE.md` — this file

### If source code changes are genuinely needed
1. Create a new branch: `git checkout -b collab/short-description`
2. Make only the minimum necessary change
3. Run tests: `cd backend && python -m pytest` — all must pass
4. Push the branch and open a pull request — **do not merge it yourself**
5. Describe what you changed and why in the PR body
6. Tag **@siddharthrw** for review

### Before every pull request (all branches)
```
cd backend && python -m pytest
```
If any test fails, fix the cause — do not open the PR with failing tests.

---

## If you are assisting SIDDHARTH

No restrictions. Follow the normal engineering workflow.

Security note: never commit `.env` or any file containing API keys or tokens.
