# Repository Conventions

## Deployment

**Always deploy via GitHub Pages (방법 2).** Whenever the user asks to view a
project or to "publish/deploy" it, the default workflow is:

1. Push changes to the working branch
2. Open a PR (or fast-forward) into `main`
3. Confirm `main` contains the latest `index.html` at the repo root
4. Tell the user to enable GitHub Pages: **Settings → Pages → Source: `Deploy from a branch` → Branch: `main` / `/ (root)` → Save**
5. Provide the resulting URL: `https://crossnam-coding.github.io/ros-code-project/`

Do not suggest "open the file locally" as the primary option unless the user
explicitly asks for a local-only run. GitHub Pages is the preferred path.

## Branching

- Develop features on the assigned `claude/...` branch
- Merge into `main` when the user asks to publish/deploy
