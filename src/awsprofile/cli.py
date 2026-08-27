"""Command-line entry point for `awsprofile`.

Thin `click` wrappers around the functions in `export_credentials.py`,
`create_credentials.py` and `prerequisites.py`. See the project README for
end-to-end usage.
"""

import sys

import click

_refresh_option = click.option(
    "--refresh",
    "-r",
    "force_refresh",
    is_flag=True,
    help="Sign in again even if the current session hasn't expired yet.",
)

# Shell function wrapper installed via `shell-init` so that plain
# `awsprofile export ...` (no manual `eval "$(...)"` typing) works directly.
# `[[ ]]`, `local` and this function-definition syntax all work identically
# in both bash and zsh, so the same snippet is printed for either shell.
_SHELL_INIT_SNIPPET = """awsprofile() {
  if [[ "$1" == "export" ]]; then
    local out
    out="$(command awsprofile "$@")" || return $?
    eval "$out"
  else
    command awsprofile "$@"
  fi
}"""


@click.group()
@click.pass_context
@click.version_option(prog_name="awsprofile", package_name="gds-idea-pkg-awsprofile")
def cli(ctx):
    """Awsprofile - manage aws credentials."""


@cli.command()
@_refresh_option
def dev(force_refresh: bool) -> None:
    """Use aws profile with dev alias temporary credentials as default profile credentials.

    Args:
        force_refresh: If set, sign in again even if the current session
            hasn't expired yet.

    Example:
        $ awsprofile dev
        $ awsprofile dev --refresh
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="dev", force_refresh=force_refresh)


@cli.command()
@_refresh_option
def prod(force_refresh: bool) -> None:
    """Use aws profile with prod alias temporary credentials as default profile credentials.

    Args:
        force_refresh: If set, sign in again even if the current session
            hasn't expired yet.

    Example:
        $ awsprofile prod
        $ awsprofile prod --refresh
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="prod", force_refresh=force_refresh)


@cli.command()
@_refresh_option
def integration(force_refresh: bool) -> None:
    """Use aws profile with integration alias temporary credentials as default profile credentials.

    Args:
        force_refresh: If set, sign in again even if the current session
            hasn't expired yet.

    Example:
        $ awsprofile integration
        $ awsprofile integration --refresh
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="integration", force_refresh=force_refresh)


@cli.command()
@_refresh_option
def bedrock(force_refresh: bool) -> None:
    """Use aws profile with bedrock alias temporary credentials as bedrockonly profile credentials.

    Unlike `dev`/`prod`/`integration`, this writes into the `bedrockonly`
    profile rather than `default`, so it never clobbers whatever role you
    currently have active in `default`.

    Args:
        force_refresh: If set, sign in again even if the current session
            hasn't expired yet.

    Example:
        $ awsprofile bedrock
        $ awsprofile bedrock --refresh
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="bedrock", export_profile="bedrockonly", force_refresh=force_refresh)


@cli.command()
@click.argument("profile", default="dev")
@click.argument("export_profile", default="default")
@_refresh_option
def profile(profile: str, export_profile: str, force_refresh: bool) -> None:
    """Log in and set aws profile temporary credentials in default profile.

    Args:
        profile: Profile or alias name to set as export_profile.
        export_profile: Profile to export credentials to, defaults to default.
        force_refresh: If set, sign in again even if the current session
            hasn't expired yet.

    Example:
        $ awsprofile profile assume-ds-role-dev-readonly
        $ awsprofile profile prod bedrockonly
        $ awsprofile profile dev default --refresh
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile=profile, export_profile=export_profile, force_refresh=force_refresh)


@cli.command()
@click.argument("alias")
@click.argument("target_name", required=False)
@_refresh_option
def export(alias: str, target_name: str, force_refresh: bool) -> None:
    """Sign in and print a shell snippet to make the session available in every terminal.

    Unlike `dev`/`prod`/`integration`/`bedrock`/`profile` (which write
    credentials into a profile you then have to reference yourself via
    `--profile`/`AWS_PROFILE`), this writes the credentials into a profile
    named `target_name` (defaults to `alias`) and prints:

        export AWS_PROFILE=<target_name>
        unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

    to stdout, meant to be `eval`'d. The `unset` matters: stale key env vars
    take precedence over `AWS_PROFILE` in the credential resolution chain,
    so without it a previous `export`'s keys could keep shadowing this one.

    Because every terminal that `eval`'d this for the same `target_name`
    reads the same file in `~/.aws/credentials`, re-running this (or
    `awsprofile profile <alias> <target_name>`, or `eval`'ing this again -
    it's idempotent) refreshes the session for all of them at once, with
    nothing further to `eval`.

    Refuses to target `"default"`, since the whole point of this command is
    to keep sessions separate from - and never disturb - whatever's
    currently active in `default`; use `dev`/`prod`/`profile` for that.

    All status output (from the underlying sign-in) goes to stderr, since
    stdout is reserved for the snippet meant to be `eval`'d.

    Args:
        alias: Profile or alias name to sign in with.
        target_name: Profile name to write credentials to, and to point
            `AWS_PROFILE` at. Defaults to `alias`.
        force_refresh: If set, sign in again even if the current session
            hasn't expired yet.

    Example:
        $ eval "$(awsprofile export prod)"
        $ eval "$(awsprofile export dev my-dev-session)"
        $ eval "$(awsprofile export prod --refresh)"
    """
    from awsprofile.export_credentials import _export_credentials

    target_name = alias if target_name is None else target_name
    if target_name == "default":
        click.echo(
            "Refusing to export to 'default' - use 'awsprofile profile'/'dev'/'prod' etc. instead.",
            err=True,
        )
        sys.exit(1)

    _export_credentials(
        profile=alias,
        export_profile=target_name,
        force_refresh=force_refresh,
        status_to_stderr=True,
    )

    click.echo(f"export AWS_PROFILE={target_name}")
    click.echo("unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN")


@cli.command(name="shell-init")
def shell_init() -> None:
    """Print a shell function that makes `awsprofile export` work without manual `eval`.

    `awsprofile export` normally requires wrapping every call in
    `eval "$(awsprofile export ...)"` so the `export AWS_PROFILE=...`/`unset
    AWS_...` snippet it prints actually takes effect in your current shell.
    This command prints a small shell function you install once, after
    which plain `awsprofile export ...` (no `eval` needed) works directly -
    the function transparently `eval`'s the output only for the `export`
    subcommand, and passes every other subcommand straight through
    unchanged.

    The generated function works the same in both bash and zsh, so there's
    no need to specify which shell you're using.

    Install once by adding a line like this to your `~/.zshrc` or
    `~/.bashrc`, then restart your shell (or `source` the rc file):

        eval "$(awsprofile shell-init)"

    Example:
        $ eval "$(awsprofile shell-init)"
        $ awsprofile export prod
        export AWS_PROFILE=prod
    """
    click.echo(_SHELL_INIT_SNIPPET)


@cli.command()
def list() -> None:
    """List aws profiles and aliases.

    Prints every `assume-ds-role-*` profile with its alias (if any), and
    every export profile that currently holds credentials, alongside the
    source profile they were signed in from.

    Example:
        $ awsprofile list
    """
    from awsprofile.export_credentials import _dict_aliases, _dict_credentials_profiles

    aliases, profiles = _dict_aliases()
    profiles_credentials = _dict_credentials_profiles()

    reversed_aliases = {profile: alias for alias, profile in aliases.items()}

    profiles_assume = [profile for profile in profiles if profile.startswith("assume-ds-role-")]

    echo_profiles_assume = [
        f"\t{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
        for profile in profiles_assume
    ]
    echo_profiles_credentials = [
        f"\t{profile} ({exported_profile})" for profile, exported_profile in profiles_credentials.items()
    ]

    echo_profiles_assume = "\n".join(echo_profiles_assume)
    click.echo(f"Available assume-ds-role profiles with aliases:\n{echo_profiles_assume}", err=False)

    echo_profiles_credentials = "\n".join(echo_profiles_credentials)
    click.echo(f"Created credentials profiles with source profiles:\n{echo_profiles_credentials}", err=False)


@cli.command()
def status() -> None:
    """Show every profile that currently holds exported credentials.

    For each profile that has ever received credentials via `dev`/`prod`/
    `integration`/`bedrock`/`profile`, prints the source profile it was
    signed in from (with its alias, if any), and whether those credentials
    are still valid, expired, or have no recorded expiration. Expiration is
    resolved live from `boto3`/`botocore` (via `_get_expiration`) rather
    than a stored value, so this may need to re-authenticate a source
    profile if its cached assume-role credentials have already expired.

    Example:
        $ awsprofile status
    """
    from awsprofile.export_credentials import _dict_aliases, _dict_credentials_profiles, _get_expiration
    from awsprofile.utils import _format_expiration

    aliases, _profiles = _dict_aliases()
    profiles_credentials = _dict_credentials_profiles()

    reversed_aliases = {profile: alias for alias, profile in aliases.items()}

    if not profiles_credentials:
        click.echo("No profiles currently hold exported credentials.")
        return

    for export_profile, source_profile in profiles_credentials.items():
        alias_suffix = f" ({reversed_aliases[source_profile]})" if source_profile in reversed_aliases else ""
        expiration_status = _format_expiration(_get_expiration(source_profile))
        click.echo(f"{export_profile}: signed in from {source_profile}{alias_suffix} - {expiration_status}")


@cli.command()
@click.argument("profile", default="default")
def clear(profile: str) -> None:
    """Remove exported credentials from a profile.

    Removes the `aws_access_key_id`, `aws_secret_access_key` and
    `aws_session_token` fields from `profile`'s section in
    `~/.aws/credentials`, and its `credentials_profile` field in
    `~/.aws/config` (both written by `dev`/`prod`/`integration`/`bedrock`/
    `profile`). It's fine to run this even if `profile` never held any
    credentials.

    Args:
        profile: Export profile to clear. Defaults to `"default"`.

    Example:
        $ awsprofile clear
        $ awsprofile clear bedrockonly
    """
    from awsprofile.export_credentials import _clear_credentials

    _clear_credentials(profile)


@cli.command()
@click.argument("profile")
@click.argument("alias")
def set(alias: str, profile: str) -> None:
    """Set alias to aws profile.

    Create or update alias field for aws profile.

    Args:
        alias: Alias name to set.
        profile: Profile name to set alias for.

    Example:
        $ awsprofile set assume-ds-role-dev-readonly dev
    """
    from awsprofile.export_credentials import _set_alias

    _set_alias(alias, profile)


@cli.command()
@click.option("--email", help="Email address used for AWS access.")
@click.option("--access-key", help="AWS access key.")
@click.option("--secret-key", help="AWS secret key.")
@click.option("--mfa", help="Full AWS mfa device name.")
@click.option("--mfa-suffix", help="Suffix appended to --email to form the full AWS mfa device name. Requires --email.")
def init(email: str, access_key: str, secret_key: str, mfa: str, mfa_suffix: str) -> None:
    """Create or update aws credentials files and fill them with profiles used by GDS IDEA team.

    Checks required external tools are installed first (via
    `_check_prerequisites`), then delegates to `_set_default_configuration`.
    All options are optional and independently gate the config fields that
    depend on them - see `_set_default_configuration` for details.

    Args:
        email: Email address used for AWS access; enables writing role_arn fields.
        access_key: AWS access key; enables writing gds-users' aws_access_key_id.
        secret_key: AWS secret key; enables writing gds-users' aws_secret_access_key.
        mfa: Full AWS mfa device name.
        mfa_suffix: Suffix appended to email to form the full mfa device name.
            Requires --email. Takes precedence over --mfa if both are given.

    Example:
        $ awsprofile init --email jane.doe@example.com --mfa-suffix "-work-phone"
        $ awsprofile init --email jane.doe@example.com --mfa jane.doe@example.com-work-phone \\
            --access-key AKIA... --secret-key ...
    """
    from awsprofile.create_credentials import _set_default_configuration
    from awsprofile.prerequisites import _check_prerequisites

    _check_prerequisites()
    _set_default_configuration(email, access_key, secret_key, mfa, mfa_suffix)
