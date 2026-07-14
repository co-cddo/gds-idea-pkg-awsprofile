import click


@click.group()
@click.pass_context
@click.version_option(prog_name="awsprofile", package_name="gds-idea-pkg-awsprofile")
def cli(ctx):
    """Awsprofile - manage aws credentials."""


@cli.command()
def dev():
    """Use aws profile with dev alias temporary credentials as default profile credentials"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="dev")


@cli.command()
def prod():
    """Use aws profile with prod alias temporary credentials as default profile credentials"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="prod")


@cli.command()
def integration():
    """Use aws profile with integration alias temporary credentials as default profile credentials"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="integration")


@cli.command()
def bedrock():
    """Use aws profile with integration alias temporary credentials as bedrockonly profile credentials"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="bedrock", export_profile="bedrockonly")


@cli.command()
@click.argument("profile", default="dev")
@click.argument("export_profile", default="default")
def profile(profile: str, export_profile: str):
    """Log in and set aws profile temporary credentials in default profile.

    Args:
        profile: Profile or alias name to set as export_profile.
        export_profile: Profile to export credentials to, defaults to default.
    """
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile=profile, export_profile=export_profile)


@cli.command()
def list():
    """List aws profiles and aliases"""
    from awsprofile.export_credentials import _dict_aliases

    aliases, profiles = _dict_aliases()

    reversed_aliases = {profile: alias for alias, profile in aliases.items()}

    profiles_assume = [profile for profile in profiles if profile.startswith("assume-ds-role-")]
    profiles_credentials = [
        profile
        for profile in profiles
        if not profile.startswith("assume-ds-role-") and reversed_aliases.get(profile, "").startswith("assume-ds-role-")
    ]

    echo_profiles_assume = [
        f"\t{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
        for profile in profiles_assume
    ]
    echo_profiles_credentials = [
        f"\t{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile
        for profile in profiles_credentials
    ]

    echo_profiles_assume = "\n".join(echo_profiles_assume)
    click.echo(f"Available assume-ds-role profiles with aliases:\n{echo_profiles_assume}", err=False)

    echo_profiles_credentials = "\n".join(echo_profiles_credentials)
    click.echo(f"Created credentials profiles with source profiles:\n{echo_profiles_credentials}", err=False)


@cli.command()
@click.argument("profile")
@click.argument("alias")
def set(alias: str, profile: str):
    """Set alias to aws profile.

    Create or update alias field for aws profile.

    Args:
        alias: Alias name to set.
        profile: Profile name to set alias for.
    """
    from awsprofile.export_credentials import _set_alias

    _set_alias(alias, profile)


@cli.command()
@click.option("--email", help="Email address used for AWS access.")
@click.option("--access-key", help="AWS access key.")
@click.option("--secret-key", help="AWS secret key.")
def init(email: str, access_key: str, secret_key: str):
    """Create or update aws credentials files and fill them with profiles used by GDS IDEA team."""
    from awsprofile.create_credentials import _set_default_configuration
    from awsprofile.prerequisites import _check_prerequisites

    _check_prerequisites()
    _set_default_configuration(email, access_key, secret_key)
