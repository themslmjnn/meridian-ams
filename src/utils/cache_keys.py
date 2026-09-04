class SessionCacheKey:
    @staticmethod
    def access_token_version_key(session_id: int) -> str:
        return f"session:token_version:{session_id}"


class UserCacheKey:
    @staticmethod
    def user_detail_key_admin(public_id: int) -> str:
        return f"users:detail:{public_id}:admin"

    @staticmethod
    def user_detail_key_staff(public_id: int) -> str:
        return f"users:detail:{public_id}:staff"

    @staticmethod
    def user_detail_key_self(public_id: int) -> str:
        return f"users:detail:{public_id}:self"


class EmailCacheKey:
    @staticmethod
    def email_detail_key(email_id: int) -> str:
        return f"emails:detail:{email_id}:admin"
