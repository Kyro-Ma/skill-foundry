# Publishing Targets

## ClawHub

Target dashboard: https://clawhub.ai/dashboard

Use the local ClawHub CLI only when publishing is explicitly enabled with `--publish-clawhub`.
The runner calls:

```bash
clawhub skill publish <skill-folder>
```

If `--clawhub-version` is provided, append:

```bash
--version <version>
```

Requirements:

- The `clawhub` command must be installed or supplied with `--clawhub-cli`.
- The user must already be authenticated, normally with `clawhub login`.
- Publish only reviewed skills that passed the runner's review stage.
- If the CLI is unavailable or authentication fails, record a skipped or failed result in `publish_results.json`; do not fail the whole run solely because publishing failed.

## GitHub

Repository listing page: https://github.com/Kyro-Ma?tab=repositories

The profile repositories page is a place to choose or create a destination repository; it is not itself an upload endpoint. Publish to a concrete repository in `owner/repo` form:

```bash
--publish-github-repo Kyro-Ma/<repo-name>
```

Requirements:

- Set `GITHUB_TOKEN` or `GH_TOKEN` with repository contents write permission.
- Use `--publish-github-branch` when the target branch is not `main`.
- Use `--publish-github-prefix` to change the repository folder prefix. The default is `skill-demand-agent-runs/<run-id>/`.

The runner uploads:

- `SKILLS_CATALOG.md`
- `SCORING_REPORT.md`
- `metadata.json`
- `publish_manifest.json`
- all reviewed generated skill folders for the run

Record per-file create/update/failure status in `publish_results.json`.
