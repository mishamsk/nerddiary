from http import HTTPStatus

from fastapi import APIRouter, HTTPException

from .....error.error import NerdDiaryError, NerdDiaryErrorCode
from ....dependencies import nds
from ....schema import UserSessionSchema

import typing as t

session_router = r = APIRouter(prefix="/session")


@r.get("/", response_model=t.List[UserSessionSchema], response_model_exclude_none=True)
async def get_sessions():
    # TODO add proper logging
    return [UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status) for ses in nds._sessions.get_all()]


@r.get("/{user_id}", response_model=UserSessionSchema, response_model_exclude_none=True)
async def get_session(user_id: str):
    # TODO add proper logging
    try:
        ses = await nds._sessions.get(user_id)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"{err!r}")

    return UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status)


@r.post("/{user_id}/unlock", response_model=UserSessionSchema, response_model_exclude_none=True)
async def unlock_session(user_id: str, password: str | None = None, key: str | None = None):
    # TODO add proper logging
    try:
        ses = await nds._sessions.get(user_id)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    bkey = None
    if key:
        bkey = key.encode()

    pass_or_key = bkey or password
    if not pass_or_key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Password or key must be present")

    try:
        await ses.unlock(pass_or_key)
    except NerdDiaryError as err:
        if err.code == NerdDiaryErrorCode.SESSION_INCORRECT_PASSWORD_OR_KEY:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=err.message)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"{err!r}")

    return UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status)
