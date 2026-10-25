"""Resolve which assessment checks are required, optional, or off."""

CHECK_NAMES = ("camera", "microphone", "identity")


def integrity_rules(assessment) -> dict[str, str]:
    raw = assessment.integrity or {}
    named = {name: raw.get(name) for name in CHECK_NAMES if raw.get(name) in {"required", "optional", "off"}}
    if assessment.proctored and not named:
        return {name: "required" for name in CHECK_NAMES}
    return {name: named.get(name, "off") for name in CHECK_NAMES}


def missing_checks(rules: dict[str, str], *, camera_ready: bool, microphone_ready: bool, identity_confirmed: bool) -> list[str]:
    present = {"camera": camera_ready, "microphone": microphone_ready, "identity": identity_confirmed}
    return [name for name, level in rules.items() if level == "required" and not present.get(name, False)]


def identity_matches(stated: str, *, display_name: str, email: str | None) -> bool:
    """Identity is confirmed only when the typed name matches the signed-in account."""
    value = stated.strip().casefold()
    if not value:
        return False
    accepted = {display_name.strip().casefold()}
    if email:
        accepted.add(email.strip().casefold())
    return value in accepted
