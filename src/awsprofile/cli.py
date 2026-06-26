import click


@click.group()
@click.pass_context
def cli(ctx):
    """Awsprofile - manage aws credentials."""


@cli.command()
def dev():
    """Log in to aws profile with dev alias"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="dev")


@cli.command()
def prod():
    """Log in to aws profile with prod alias"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="prod")


@cli.command()
def integration():
    """Log in to aws profile with integration alias"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile="integration")


@cli.command()
@click.argument("profile", default="dev")
def profile(profile: str):
    """Log in to aws profile"""
    from awsprofile.export_credentials import _export_credentials

    _export_credentials(profile=profile)


@cli.command()
def list():
    """List aws profiles"""
    from awsprofile.export_credentials import _dict_aliases

    aliases, profiles = _dict_aliases()

    reversed_aliases = {profile: alias for alias, profile in aliases.items()}
    echo_profiles = [
        f"{profile} ({reversed_aliases[profile]})" if profile in reversed_aliases else profile for profile in profiles
    ]
    click.echo(f"Available profiles:\n{'\n'.join(echo_profiles)}", err=True)


@cli.command()
@click.argument("profile")
@click.argument("alias")
def set(alias: str, profile: str):
    """List aws profiles"""
    from awsprofile.export_credentials import _set_alias

    _set_alias(alias, profile)


@cli.command()
@click.option("--email")
@click.option("--access-key")
@click.option("--secret-key")
def init(email: str, access_key: str, secret_key: str):
    """List aws profiles"""
    from awsprofile.create_credentials import _set_default_configuration

    _set_default_configuration(email, access_key, secret_key)
