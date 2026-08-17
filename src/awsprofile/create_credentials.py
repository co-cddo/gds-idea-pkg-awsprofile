from awsprofile.utils import _execute_command


def _set_default_configuration(email: str = None, access_key: str = None, secret_key: str = None, mfa: str = None):
    """Create or update .aws folder in home directory with config and credentials files.

    Create or update aws credentials files and fill them with profiles used by GDS IDEA team.

    Args:
        email: If provided, creates or updates profiles role_arn field.
        access_key: If provided, creates or updates gds-users profile aws_access_key_id field.
        secret_key: If provided, creates or updates gds-users profile secret_key field.
        mfa: Creates or updates profiles mfa field. If an email address is provided,
        only the suffix can be provided, otherwise the full MFA name must be provided.
    """
    org_account = "622626885786"
    mfa = email + mfa if mfa is not None and not mfa.startswith(email) and email else mfa
    if access_key:
        _execute_command(["aws", "configure", "set", "profile.gds-users.aws_access_key_id", access_key])
    if secret_key:
        _execute_command(["aws", "configure", "set", "profile.gds-users.aws_secret_access_key", secret_key])
    if mfa:
        _execute_command(
            ["aws", "configure", "set", "profile.gds-users.mfa_serial", f"arn:aws:iam::{org_account}:mfa/{mfa}"]
        )

    profiles_base = ["default", "gds-users", "bedrockonly"]
    profiles_env = {
        "prod": [("admin", "proda"), ("poweraccess", "prodp"), ("readonly", "prod")],
        "dev": [("admin", "deva"), ("poweraccess", "dev"), ("readonly", "devr"), ("bedrockonly", "bedrock")],
        "integration": [("admin", "integration")],
    }
    profiles_accounts = {"prod": "588077357019", "dev": "992382722318", "integration": "539502489680"}
    fields_all = [("output", "json"), ("region", "eu-west-2"), ("duration_seconds", "28800")]
    for profile in profiles_base:
        for field, value in fields_all:
            _execute_command(["aws", "configure", "set", f"profile.{profile}.{field}", value])
    for env, profiles in profiles_env.items():
        for profile, alias in profiles:
            for field, value in fields_all:
                _execute_command(["aws", "configure", "set", f"profile.assume-ds-role-{env}-{profile}.{field}", value])
            _execute_command(
                ["aws", "configure", "set", f"profile.assume-ds-role-{env}-{profile}.source_profile", "gds-users"]
            )
            _execute_command(["aws", "configure", "set", f"profile.assume-ds-role-{env}-{profile}.alias", alias])

    if email:
        email_prefix = email.split("@", 1)[0]
        for env, profiles in profiles_env.items():
            for profile, _alias in profiles:
                _execute_command(
                    [
                        "aws",
                        "configure",
                        "set",
                        f"profile.assume-ds-role-{env}-{profile}.role_arn",
                        f"arn:aws:iam::{profiles_accounts[env]}:role/{email_prefix}-{profile}",
                    ]
                )

    if mfa:
        for env, profiles in profiles_env.items():
            for profile, _alias in profiles:
                _execute_command(
                    [
                        "aws",
                        "configure",
                        "set",
                        f"profile.assume-ds-role-{env}-{profile}.mfa_serial",
                        f"arn:aws:iam::{org_account}:mfa/{mfa}",
                    ]
                )
