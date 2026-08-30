class EmailCacheKey:
    @staticmethod
    def email_detail_key(email_id: int) -> str:
        return f"emails:{email_id}:admin"
