"""Command-line entry point for `awsprofile`.

Thin `click` wrappers around the functions in `export_credentials.py`,
`create_credentials.py` and `prerequisites.py`. See the project README for
end-to-end usage.
"""

import click


@click.group()
@click.pass_context
@click.version_option(prog_name="awsprofile", package_name="gds-idea-pkg-awsprofile")
def cli(ctx):
    """Awsprofile - manage aws credentials."""


@cli.command()
def dev() -> None:
    """Use aws profile with dev alias temporary credentials as default profile credentials.

    Example:
        $ awsprofile dev
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="dev")


@cli.command()
def prod() -> None:
    """Use aws profile with prod alias temporary credentials as default profile credentials.

    Example:
        $ awsprofile prod
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="prod")


@cli.command()
def integration() -> None:
    """Use aws profile with integration alias temporary credentials as default profile credentials.

    Example:
        $ awsprofile integration
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="integration")


@cli.command()
def bedrock() -> None:
    """Use aws profile with bedrock alias temporary credentials as bedrockonly profile credentials.

    Unlike `dev`/`prod`/`integration`, this writes into the `bedrockonly`
    profile rather than `default`, so it never clobbers whatever role you
    currently have active in `default`.

    Example:
        $ awsprofile bedrock
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="bedrock", export_profile="bedrockonly")


@cli.command()
@click.argument("profile", default="dev")
@click.argument("export_profile", default="default")
def profile(profile: str, export_profile: str) -> None:
    """Log in and set aws profile temporary credentials in default profile.

    Args:
        profile: Profile or alias name to set as export_profile.
        export_profile: Profile to export credentials to, defaults to default.

    Example:
        $ awsprofile profile assume-ds-role-dev-readonly
        $ awsprofile profile prod bedrockonly
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile=profile, export_profile=export_profile)


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
