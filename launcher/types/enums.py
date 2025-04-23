from enum import Enum

class VersionType(Enum):
    SNAPSHOT = "snapshot"
    RELEASE = "release"
    OLD_ALPHA = "old_alpha"

class MachineArch(Enum):
    X86 = "x86"
    X64 = "x64"
