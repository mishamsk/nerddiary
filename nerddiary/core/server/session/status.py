import enum


@enum.unique
class UserSessionStatus(enum.IntEnum):
    NEW = 0
    LOCKED = 10
    UNLOCKED = 20
    CONFIGURED = 30
