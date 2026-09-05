class SessionCacheKey:
    @staticmethod
    def access_token_version_key(session_id: int) -> str:
        return f"session:token_version:{session_id}"

    @staticmethod
    def pack_atv_cache(atv: int, credentials_id: int) -> str:
        return f"{atv}:{credentials_id}"

    @staticmethod
    def unpack_atv_cache(cached: str) -> tuple[int, int]:
        """
        Unpack the cached ATV string back into (atv, credentials_id).

        Raises ValueError if the cache value is malformed — treated as a cache
        miss by the caller, which will fall through to the DB path.
        """

        try:
            atv_str, credentials_id_str = cached.split(":", 1)

            return int(atv_str), int(credentials_id_str)

        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Malformed ATV cache value: {cached!r}") from exc


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
