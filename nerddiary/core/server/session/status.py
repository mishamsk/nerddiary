import enum


@enum.unique
class UserSessionStatus(enum.IntEnum):
    """Defines user session status. Numeric order matters. NEW must preceed LOCKED, and LOCKED must preceed further statuses"""

    NEW = 0
    LOCKED = 10
    UNLOCKED = 20
    CONFIGURED = 30
