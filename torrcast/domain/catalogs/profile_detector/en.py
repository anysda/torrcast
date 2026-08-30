"""English captions of the profile-detector cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the profile-detector cluster."""
    return {
        "profile_detector.named_manually": "manually named: receiver_profile={profile_key}",
        "profile_detector.unknown_named_profile": (
            'no profile named "{name}" - falling back to cautious'
        ),
        "profile_detector.no_passport_receiver": (
            "no receiver with a passport - falling back to cautious"
        ),
        "profile_detector.no_response": "receiver did not respond - falling back to cautious",
        "profile_detector.no_introduction": (
            "receiver did not introduce itself - falling back to cautious"
        ),
        "profile_detector.by_passport_prefix": "by passport:",
    }
