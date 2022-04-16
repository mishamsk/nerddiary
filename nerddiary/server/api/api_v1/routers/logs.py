from http import HTTPStatus

from fastapi import APIRouter, HTTPException

from .....error.error import NerdDiaryError, NerdDiaryErrorCode
from ....dependencies import nds
from ....schema import PollLogSchema, PollLogsSchema

logs_router = r = APIRouter(prefix="/logs")


@r.get("/{user_id}/{log_id}", response_model=PollLogSchema)
async def get_single_log(user_id: str, log_id: int):
    # TODO add proper logging
    try:
        ses = await nds._sessions.get(user_id)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    ret = None
    try:
        ret = await ses.get_poll_data(log_id=log_id)
    except NerdDiaryError as err:
        if err.code == NerdDiaryErrorCode.SESSION_INCORRECT_STATUS:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=err.message)
        if err.code == NerdDiaryErrorCode.LOGS_LOG_ID_NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=err.message)

        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    return ret.logs[0]


@r.get("/{user_id}", response_model=PollLogsSchema)
async def get_logs(user_id: str, poll_name: str | None = None, count: int | None = None, skip: int | None = None):
    # TODO add proper logging
    try:
        ses = await nds._sessions.get(user_id)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    ret = None
    try:
        ret = await ses.get_poll_data(poll_name=poll_name, count=count, skip=skip)
    except NerdDiaryError as err:
        if err.code == NerdDiaryErrorCode.SESSION_INCORRECT_STATUS:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=err.message)
        if err.code == NerdDiaryErrorCode.LOGS_LOG_ID_NOT_FOUND:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=err.message)

        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    return ret


@r.post("/{user_id}/batch_add")
async def batch_add(user_id: str, data: PollLogsSchema):
    # TODO add proper logging
    try:
        ses = await nds._sessions.get(user_id)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    ret = 0
    try:
        ret = await ses.log_poll_data(data=data)
    except NerdDiaryError as err:
        err_code = HTTPStatus.INTERNAL_SERVER_ERROR
        if err.code == NerdDiaryErrorCode.SESSION_INCORRECT_STATUS:
            err_code = HTTPStatus.UNAUTHORIZED
        raise HTTPException(status_code=err_code, detail=f"{err!r}")

    return {"result": "success", "count": ret}
