from dataclasses import dataclass
from datetime import datetime
from .enums import VersionType


@dataclass
class VersionMeta:
    """
    Class representing a version with a timestamp.
    """
    id: str
    type_: VersionType
    url: str
    time: datetime
    releaseTime: datetime
    sha1: str
    complianceLevel: int

    def __post_init__(self):
        assert self.type_ in VersionType, "Invalid version type, must be one of VersionType"
        assert isinstance(self.time, datetime), "Time must be a datetime object"
        assert isinstance(self.releaseTime, datetime), "Release time must be a datetime object"
        assert isinstance(self.sha1, str), "SHA1 must be a string"
        assert isinstance(self.complianceLevel, int), "Compliance level must be an integer"
        assert isinstance(self.url, str), "URL must be a string"

        assert self.id.strip(), "ID must not be empty"
        assert self.url.strip(), "URL must not be empty"
        assert self.sha1.strip(), "SHA1 must not be empty"
        assert self.complianceLevel >= 0, "Compliance level must be non-negative"
