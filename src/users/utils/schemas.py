from dataclasses import dataclass


@dataclass
class LoadOptionsSchema:
    load_identity: bool = False
    load_sessions: bool = False
    load_activation: bool = False
    load_login_lockout: bool = False
    load_email_change: bool = False
    load_password_reset: bool = False
