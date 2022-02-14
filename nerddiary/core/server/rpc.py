import enum


@enum.unique
class RPCErrors(enum.IntEnum):
    SESSION_NOT_FOUND = -1
    ERROR_GETTING_SESSION = -1001
