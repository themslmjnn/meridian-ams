from dataclasses import dataclass


@dataclass
class LoadOptionsSchema:
    load_identity: bool | None = False
    load_sessions: bool | None = False
    load_activation: bool | None = False
    load_login_lockout: bool | None = False
    load_email_change: bool | None = False
    load_password_reset: bool | None = False
