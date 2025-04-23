from dataclasses import dataclass
from datetime import datetime
from .enums import MachineArch

@dataclass
class JREAvailability:
    group: int
    progress: int

    def __post_init__(self):
        assert isinstance(self.progress, int)
        assert isinstance(self.group, int)

        assert self.progress >= 0 <= 100, "Progress must be between 0 and 100"
        assert self.group >= 0, "Group must be non-negative"

@dataclass
class JREManifest:
    sha1: str
    size: int
    url: str

    def __post_init__(self):
        assert isinstance(self.sha1, str)
        assert isinstance(self.size, int)
        assert isinstance(self.url, str)

@dataclass
class JREVersion:
    name: str
    released: datetime

    def __post_init__(self):
        assert isinstance(self.name, str)
        assert isinstance(self.released, datetime)


@dataclass
class JRE:
    """
    Class representing a Java Runtime Environment (JRE) version.
    """
    arch: MachineArch
    availability: JREAvailability
    manifest: JREManifest
    version: JREVersion
