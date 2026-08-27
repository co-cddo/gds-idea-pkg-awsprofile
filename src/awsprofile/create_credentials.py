from awsprofile.utils import _config_set, _credentials_set


def _set_default_configuration(
    email: str = None,
    access_key: str = None,
    secret_key: str = None,
    mfa: str = None,
    mfa_suffix: str = None,
):
    """Create or update .aws/config file with profiles used by the GDS IDEA team.

    Args:
        email: If provided, creates or updates profiles role_arn field.
        access_key: If provided, creates or updates gds-users profile aws_access_key_id field.
        secret_key: If provided, creates or updates gds-users profile secret_key field.
        mfa: Full AWS MFA device name to set as the mfa_serial field.
        mfa_suffix: Suffix appended to email to form the full MFA device name. Requires
        email to also be provided. Takes precedence over mfa if both are given.
    """
    org_account = "622626885786"

    if mfa_suffix is not None:
        if not email:
            raise ValueError("mfa_suffix requires email to be provided")
        mfa = f"{email}{mfa_suffix}"

    email_prefix = email.split("@", 1)[0] if email else None
    mfa_serial = f"arn:aws:iam::{org_account}:mfa/{mfa}" if mfa else None

    common_fields = {"output": "json", "region": "eu-west-2", "duration_seconds": "28800"}

    # Explicit mapping of every profile name to the exact fields/values written to
    # ~/.aws/config. A `None` value means the field is skipped (only set when the
    # corresponding argument - access_key/secret_key/email/mfa - was provided).
    profiles_fields = {
        "default": {**common_fields},
        "gds-users": {
            **common_fields,
            "mfa_serial": mfa_serial,
        },
        "bedrockonly": {**common_fields},
        "assume-ds-role-prod-admin": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "proda",
            "role_arn": f"arn:aws:iam::588077357019:role/{email_prefix}-admin" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-prod-poweraccess": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "prodp",
            "role_arn": f"arn:aws:iam::588077357019:role/{email_prefix}-poweraccess" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-prod-readonly": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "prod",
            "role_arn": f"arn:aws:iam::588077357019:role/{email_prefix}-readonly" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-dev-admin": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "deva",
            "role_arn": f"arn:aws:iam::992382722318:role/{email_prefix}-admin" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-dev-poweraccess": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "dev",
            "role_arn": f"arn:aws:iam::992382722318:role/{email_prefix}-poweraccess" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-dev-readonly": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "devr",
            "role_arn": f"arn:aws:iam::992382722318:role/{email_prefix}-readonly" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-dev-bedrockonly": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "bedrock",
            "role_arn": f"arn:aws:iam::992382722318:role/{email_prefix}-bedrockonly" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
        "assume-ds-role-integration-admin": {
            **common_fields,
            "source_profile": "gds-users",
            "alias": "integration",
            "role_arn": f"arn:aws:iam::539502489680:role/{email_prefix}-admin" if email_prefix else None,
            "mfa_serial": mfa_serial,
        },
    }

    # Explicit mapping of the gds-users credentials fields written to
    # ~/.aws/credentials (access keys live there, not in ~/.aws/config).
    credentials_fields = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
    }

    for field, value in credentials_fields.items():
        if value is not None:
            _credentials_set("gds-users", field, value)

    for profile, fields in profiles_fields.items():
        for field, value in fields.items():
            if value is not None:
                _config_set(profile, field, value)
