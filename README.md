# gds-idea-pkg-awsprofile

CLI tool for AWS credential file management and signing in to GDS IDEA AWS profiles.

## How this works

This tool signs you in to an AWS role via MFA, then writes the resulting
temporary session credentials directly to `~/.aws/credentials` on disk,
rather than only exporting them into your current shell's environment.

Because credentials live on disk, they're not scoped to a single shell:

- They persist after closing the terminal, opening new tabs, restarting
  your machine, etc. — right up until they expire (8 hours) or you
  overwrite them by signing in again.
- **All processes on your machine that read the `default` profile share
  the same credentials, unless you explicitly target a different
  profile.** Running `awsprofile prod` in one terminal changes what every
  other terminal, script, IDE plugin, or tool sees as `default` too —
  including ones you're not actively looking at. Only one role can be
  "active" in `default` at a time.

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

## Concepts

A few terms used throughout this doc and the CLI's own help text:

- **Profile** — a named entry in `~/.aws/config`/`~/.aws/credentials` that
  AWS tooling understands directly, e.g. `assume-ds-role-prod-readonly`.
- **Alias** — a short nickname for a profile that this tool manages (a
  custom `alias` field in `~/.aws/config`), e.g. `prod` for
  `assume-ds-role-prod-readonly`. Lets you type `awsprofile prod` instead
  of the full profile name.
- **Export profile** — the profile that receives the temporary session
  credentials (access key, secret key, session token) once you've signed
  in. Defaults to `default`, since that's what most AWS tooling reads
  automatically with no extra configuration — see "How this works" above
  for what that implies.

## Getting started

1. Configure AWS credentials and config files:
   - If you already have a `gds-users` profile set up: \
     `awsprofile init --email {your-aws-account-email} --mfa {your-aws-account-mfa}`
   - Otherwise: \
     `awsprofile init --email {your-aws-account-email} --mfa {your-aws-account-mfa} --access-key {access key from credentials file} --secret-key {secret key from credentials file}`
   - If your MFA device name is your email plus a suffix, you can pass
     just the suffix instead of the full device name: \
     `awsprofile init --email {your-aws-account-email} --mfa-suffix {suffix after your email in the mfa device name}`
2. Check what's available:
   - List profiles and aliases, and any existing export mappings: \
     `awsprofile list`
3. Sign in:
   - Using an alias shortcut: \
     `awsprofile dev` / `awsprofile prod` / `awsprofile integration` / `awsprofile bedrock`
   - Or explicitly by profile/alias name (optionally targeting a
     specific export profile instead of `default`): \
     `awsprofile profile {profile or alias name} {(optional) export profile name}`
4. (Optional) Give a profile your own alias: \
   `awsprofile set {profile name} {alias name}`

## Commands

| Command | What it does |
| --- | --- |
| `awsprofile init` | Creates/updates `~/.aws/config` and `~/.aws/credentials` with the GDS IDEA profile set. Accepts `--email`, `--mfa`/`--mfa-suffix`, and `--access-key`/`--secret-key` if `gds-users` isn't already configured. |
| `awsprofile list` | Lists available `assume-ds-role-*` profiles with their aliases, and shows which export profiles currently hold credentials from which source profile. |
| `awsprofile status` | Shows every export profile that currently holds credentials, the source profile (and alias) they were signed in from, and whether those credentials are still valid, expired, or have no recorded expiration. |
| `awsprofile set {profile} {alias}` | Assigns a nickname (`alias`) to an existing profile. |
| `awsprofile profile {profile\|alias} {export_profile=default}` | Signs in to the given profile or alias and writes temporary credentials into `export_profile` (`default` unless specified). |
| `awsprofile dev` / `prod` / `integration` | Shortcuts for `awsprofile profile <alias>`, writing into `default`. |
| `awsprofile bedrock` | Shortcut for signing in to the `bedrock` alias, but writes into the **`bedrockonly`** profile — **not `default`**. This is the one command here that doesn't affect `default` at all. |
| `awsprofile clear {export_profile=default}` | Removes the access key/secret key/session token and `credentials_profile` previously written to `export_profile` by any of the sign-in commands above. |

## Good to know

- **`default` is shared** — see "How this works" above. `dev`/`prod`/`integration`/`profile` (with no export profile given) all overwrite the same `default` profile, globally, across every terminal and tool on your machine.
- **Sessions last 8 hours.** Re-run the same command to refresh once it expires.
- **`bedrock` is the exception** — it writes to `bedrockonly`, so it won't clobber whatever role you have active in `default`, but it also means other tools that only look at `default` won't see it.

## Troubleshooting

- **`aws: command not found` / missing tools error** — install the AWS CLI (`brew install awscli`) and re-run; `awsprofile init` checks for this up front.
- **`Profile or alias 'x' does not exist`** — run `awsprofile list` to see what's actually available, and double check spelling/casing.
- **An unexpected Python traceback during sign-in** — this is a known rough edge (see [issue #7](https://github.com/co-cddo/gds-idea-pkg-awsprofile/issues/7)); common causes are an expired or not-yet-registered MFA device, or signing in again before the previous session fully expired. Re-running the command usually resolves it; if it persists, check that `awsprofile init --email ...` was run with the correct account email.

## Licence

[MIT License](LICENCE)

## Contributing

### Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python package management
- [git](https://git-scm.com/)
- [gitleaks](https://github.com/gitleaks/gitleaks) for pre-commit secret scanning (`brew install gitleaks`)

### Setup

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

### Development

#### Running tests

```bash
uv run pytest
```

#### Running linting manually

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

#### Pre-commit hooks

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

### Versioning

This project uses [hatch-vcs](https://github.com/ofek/hatch-vcs) for
automatic versioning from git tags. Versions are never set manually.

On merge to `main`, the auto-release workflow creates a new tag based on
PR labels:

- `bump:major` — major version bump
- `bump:minor` — minor version bump
- (default) — patch version bump
