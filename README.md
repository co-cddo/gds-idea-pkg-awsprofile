# gds-idea-pkg-awsprofile

CLI tool for aws credential files management and aws profile sign in.

- Create aws credentials and config files and fill them with GDS IDEA aws profiles
- Log in to selected profile and set it as default

## Initial setup

1. Configure AWS credentials and config files
   - If you already have gds-users profile set up: \
   `awsprofile init —email {your-aws-account-email}`
   - Otherwise: \
   `awsprofile init —email {your-aws-account-email} —access-key {access key from credentials file} —secret-key {secret key from credentials file}`
2. Sign up to AWS
   - Check current profiles and aliases: \
   `awsprofile list`
   - Sign up to profile: \
   `awsprofile profile {profile or alias name}`
   - Sign up to `dev`/`prod`/`integration` aliases \
   `awsprofile dev/prod/integration`
   - Set up profile alias \
   `awsprofile set {profile name} {alias name}`

## Installation

`awsprofile` is installed as a global CLI tool, not as a per-project dependency. Install it via the [GDS IDEA package index](https://co-cddo.github.io/gds-idea-pypi/).

**Recommended — using `idea-tools`** (see the [index page](https://co-cddo.github.io/gds-idea-pypi/) for one-time setup):

```bash
idea-tools install gds-idea-pkg-awsprofile
```

**Alternative — without `idea-tools`:**

```bash
uv tool install gds-idea-pkg-awsprofile --index gds-idea=https://co-cddo.github.io/gds-idea-pypi/simple/
```

To upgrade to the latest version:

```bash
idea-tools upgrade gds-idea-pkg-awsprofile
# or without idea-tools:
uv tool upgrade gds-idea-pkg-awsprofile
```

If you previously installed from a git URL, switch to the index:

```bash
idea-tools install gds-idea-pkg-awsprofile --reinstall
```

Verify it's working:

```bash
awsprofile --version
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python package management
- [git](https://git-scm.com/)
- [gitleaks](https://github.com/gitleaks/gitleaks) for pre-commit secret scanning (`brew install gitleaks`)

## Getting started

1. Clone the repository:

   ```bash
   git clone git@github.com:co-cddo/gds-idea-pkg-awsprofile.git
   cd gds-idea-pkg-awsprofile
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Set up pre-commit hooks:

   ```bash
   uv run pre-commit install
   ```

   This is done automatically when the project is first scaffolded.
   Pre-commit runs [ruff](https://docs.astral.sh/ruff/) on every commit
   to auto-fix lint issues and enforce formatting.

## Development

### Running tests

```bash
uv run pytest
```

### Running linting manually

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

### Pre-commit hooks

Pre-commit hooks run automatically on `git commit`. They will:

- **Auto-fix** lint issues detected by `ruff check --fix`
- **Auto-format** code with `ruff format`
- **Check** YAML/TOML syntax, trailing whitespace, merge conflicts
- **Scan** for leaked secrets with gitleaks
- **Prevent** direct commits to `main`

If files are modified by the hooks, the commit will be aborted.
Review the changes, `git add` them, and commit again.

To run hooks against all files manually:

```bash
uv run pre-commit run --all-files
```

## Versioning

This project uses [hatch-vcs](https://github.com/ofek/hatch-vcs) for
automatic versioning from git tags. Versions are never set manually.

On merge to `main`, the auto-release workflow creates a new tag based on
PR labels:

- `bump:major` — major version bump
- `bump:minor` — minor version bump
- (default) — patch version bump

## Licence

[MIT License](LICENCE)
