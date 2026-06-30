import click


@click.group()
@click.pass_context
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
@click.argument("profile", default="dev", help="AWS profile or alias name.")
def profile(profile: str):
    """Use aws profile temporary credentials as default profile credentials"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile=profile)


@cli.command()
def list():
    """List aws profiles and aliases"""
    from awsprofile.export_credentials import _dict_aliases

    aliases, profiles = _dict_aliases()

    reversed_aliases = {profile: alias for alias, profile in aliases.items()}
    echo_profiles = [
        f"{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile for profile in profiles
    ]
    click.echo(f"Available profiles:\n{'\n'.join(echo_profiles)}", err=True)


@cli.command()
@click.argument("profile", help="AWS profile name.")
@click.argument("alias", help="AWS profile alias name.")
def set(alias: str, profile: str):
    """Set aws profile alias"""
    from awsprofile.export_credentials import _set_alias

    _set_alias(alias, profile)


@cli.command()
@click.option("--email", help="Email address used for AWS access.")
@click.option("--access-key", help="AWS access key.")
@click.option("--secret-key", help="AWS secret key.")
def init(email: str, access_key: str, secret_key: str):
    """Create or update aws profiles config and credentials files"""
    from awsprofile.create_credentials import _set_default_configuration
    from awsprofile.prerequisites import _check_prerequisites

    _check_prerequisites()
    _set_default_configuration(email, access_key, secret_key)
