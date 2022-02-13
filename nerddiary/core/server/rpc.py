import enum


@enum.unique
class RPCErrors(enum.IntEnum):
    SESSION_NOT_FOUND = -1
    PASSWORD_AND_KEY_MISSING = -2
