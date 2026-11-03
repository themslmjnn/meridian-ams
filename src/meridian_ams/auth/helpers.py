from ua_parser import parse


def describe_user_agent(user_agent: str | None) -> str:
    """Return a short, human-readable device description like 'Chrome on Windows'."""

    if not user_agent:
        return "Unknown device"

    result = parse(user_agent[:512])
    browser = result.user_agent.family if result.user_agent else None
    os_name = result.os.family if result.os else None

    parts = [p for p in (browser, os_name) if p and p != "Other"]

    return " on ".join(parts) if parts else "Unknown device"
