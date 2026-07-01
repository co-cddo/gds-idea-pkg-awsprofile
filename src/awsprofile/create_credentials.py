import subprocess


def _set_default_configuration(email: str = None, access_key: str = None, secret_key: str = None):
    """Create or update .aws folder in home directory with config and credentials files.

    Create or update aws credentials files and fill them with profiles used by GDS IDEA team.

    Args:
        email: If provided, creates or updates profiles role_arn and mfa_serial fields.
        access_key: If provided, creates or updates gds-users profile aws_access_key_id field.
        secret_key: If provided, creates or updates gds-users profile secret_key field.
    """
    org_account = "622626885786"
    if access_key:
        subprocess.run(
            ["aws", "configure", "set", "profile.gds-users.aws_access_key_id", access_key],
            check=True,
            capture_output=True,
            text=True,
        )
    if secret_key:
        subprocess.run(
            ["aws", "configure", "set", "profile.gds-users.aws_secret_access_key", secret_key],
            check=True,
            capture_output=True,
            text=True,
        )
    if email:
        subprocess.run(
            ["aws", "configure", "set", "profile.gds-users.mfa_serial", f"arn:aws:iam::{org_account}:mfa/{email}"],
            check=True,
            capture_output=True,
            text=True,
        )

    profiles_base = ["default", "gds-users"]
    profiles_env = {
        "prod": [("admin", "proda"), ("poweraccess", "prodp"), ("readonly", "prod")],
        "dev": [("admin", "deva"), ("poweraccess", "dev"), ("readonly", "devr")],
        "integration": [("admin", "integration")],
    }
    profiles_accounts = {"prod": "588077357019", "dev": "992382722318", "integration": "539502489680"}
    fields_all = [("output", "json"), ("region", "eu-west-2"), ("duration_seconds", "28800")]
    for profile in profiles_base:
        for field, value in fields_all:
            subprocess.run(
                ["aws", "configure", "set", f"profile.{profile}.{field}", value],
                check=True,
                capture_output=True,
                text=True,
            )
    for env, profiles in profiles_env.items():
        for profile, alias in profiles:
            for field, value in fields_all:
                subprocess.run(
                    ["aws", "configure", "set", f"profile.assume-ds-role-{env}-{profile}.{field}", value],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            subprocess.run(
                ["aws", "configure", "set", f"profile.assume-ds-role-{env}-{profile}.source_profile", "gds-users"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["aws", "configure", "set", f"profile.assume-ds-role-{env}-{profile}.alias", alias],
                check=True,
                capture_output=True,
                text=True,
            )

    if email:
        email_prefix = email.split("@", 1)[0]
        for env, profiles in profiles_env.items():
            for profile, _alias in profiles:
                subprocess.run(
                    [
                        "aws",
                        "configure",
                        "set",
                        f"profile.assume-ds-role-{env}-{profile}.role_arn",
                        f"arn:aws:iam::{profiles_accounts[env]}:role/{email_prefix}-{profile}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    [
                        "aws",
                        "configure",
                        "set",
                        f"profile.assume-ds-role-{env}-{profile}.mfa_serial",
                        f"arn:aws:iam::{org_account}:mfa/{email}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
