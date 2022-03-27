import enum
import sys

from typing import Any


@enum.unique
class NerdDiaryErrorCode(enum.IntEnum):
    # All ND specific values must be greater > -32000
    UNDEFINED = -1
    # Session error codes
    SESSION_INTERNAL_ERROR_INCORRECT_STATE = -101
    SESSION_INCORRECT_STATUS = -102
    SESSION_INCORRECT_PASSWORD_OR_KEY = -103
    SESSION_NO_LOCK = -104
    SESSION_DATA_PARSE_ERROR = -105
    SESSION_POLL_NOT_FOUND = -106
    SESSION_POLL_ANSWER_UNSUPPORTED_VALUE = -107
    SESSION_POLL_NO_DEFAULT_VALUE = -108
    SESSION_POLL_RUN_ID_NOT_FOUND = -109
    SESSION_INVALID_USER_CONFIGURATION = -110
    SESSION_POLL_ALREADY_ACTIVE = -111
    # Workflow
    WORKFLOW_FAILED_DESERIALIZE = -201
    # XML-RPC Error codes
    RPC_PARSE_ERROR = -32700
    RPC_INVALID_REQUEST = -32600
    RPC_METHOD_NOT_FOUND = -32601
    RPC_INVALID_PARAMS = -32602
    RPC_INTERNAL_ERROR = -32603
    RPC_SERVER_ERROR = -32000


ND_ERROR_MESSAGES = {
    NerdDiaryErrorCode.SESSION_INTERNAL_ERROR_INCORRECT_STATE: "System error, incorrect internal state: {}",
    NerdDiaryErrorCode.SESSION_NO_LOCK: "Data corruption: Session found but data lock is missing",
    NerdDiaryErrorCode.SESSION_DATA_PARSE_ERROR: "Data corruption: Error parsing session data category <{}>",
    NerdDiaryErrorCode.SESSION_INCORRECT_STATUS: "Inccorect session status: {}",
    NerdDiaryErrorCode.SESSION_POLL_NOT_FOUND: "Poll with the name <{}> wasn't found",
    NerdDiaryErrorCode.SESSION_POLL_RUN_ID_NOT_FOUND: "Poll with run id <{}> wasn't found",
    NerdDiaryErrorCode.SESSION_POLL_ANSWER_UNSUPPORTED_VALUE: "Unsupported poll answer value was provided",
    NerdDiaryErrorCode.SESSION_POLL_NO_DEFAULT_VALUE: "Current question has no default value",
    NerdDiaryErrorCode.SESSION_POLL_ALREADY_ACTIVE: "A poll <{}> is already active. Can't start the second poll because it is set to 'Once per day'",
    NerdDiaryErrorCode.SESSION_INCORRECT_PASSWORD_OR_KEY: "Incorrect password or key",
    NerdDiaryErrorCode.SESSION_INVALID_USER_CONFIGURATION: "User configuration file is not valid",
    NerdDiaryErrorCode.WORKFLOW_FAILED_DESERIALIZE: "Data corruption: Error parsing serialized workflow data",
    NerdDiaryErrorCode.UNDEFINED: "Unspecified session error",
}


class NerdDiaryError(Exception):
    def __init__(
        self,
        code: NerdDiaryErrorCode = NerdDiaryErrorCode.UNDEFINED,
        ext_message: str | None = None,
        data: Any | None = None,
    ) -> None:
        self.code = code
        self.data = data

        mes = ND_ERROR_MESSAGES.get(code, code.name)
        if ext_message is not None:
            self.message = mes.format(ext_message)
        else:
            self.message = mes

        super().__init__(code, self.message, data, sys.exc_info())
