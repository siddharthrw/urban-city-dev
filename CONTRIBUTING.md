# Contributing to City Planning OS

Welcome! This guide is written for non-technical contributors.

---

## What you can contribute

You make this project smarter by adding **data and documentation** — not by changing the code.

| What | Where to put it | Examples |
|------|----------------|---------|
| New datasets | `data/` | Bus routes CSV, heritage sites GeoParquet, traffic counts Excel |
| Planning rules | `rules/` | Road design standards YAML, zoning guidelines |
| Research & notes | `docs/` | Policy documents, standards PDFs, meeting notes |

---

## What you must not touch

- `frontend/` and `backend/` — the application source code
- Any file ending in `.ts`, `.tsx`, `.py`, `.js`
- `package.json`, `pyproject.toml`, `vite.config.ts`
- `.env` files — these contain private credentials

If you accidentally open one of these files, close it without saving.

---

## How to contribute (step by step)

### For data and documentation (normal workflow)

1. Make sure you are on a fresh branch from `main`:
   ```
   git checkout main
   git pull
   git checkout -b data/what-you-are-adding
   ```
2. Add your files to `data/` or `docs/`
3. Commit:
   ```
   git add .
   git commit -m "data: brief description of what you added"
   ```
4. Push and open a pull request on GitHub
5. Wait for Siddharth to review and merge — do not merge yourself

### For source code changes (only if necessary)

1. Create a branch named `collab/short-description`
2. Make your change
3. Run the test suite and confirm it passes (ask Claude to do this for you)
4. Open a pull request describing exactly what changed and why
5. Tag @siddharthrw — he must approve before anything merges

---

## Rules enforced automatically

- **Every pull request requires Siddharth's approval** before it can merge
- **Tests run automatically** on every pull request — a failing test blocks the merge
- **Source code files** are owned by @siddharthrw — GitHub will request his review if you touch them

---

## Questions?

If you're unsure whether something is safe to change, ask your Claude assistant first — it has read the project guardrails and will tell you.
