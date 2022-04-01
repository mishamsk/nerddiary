from http import HTTPStatus

from fastapi import APIRouter, HTTPException

from .....error.error import NerdDiaryError
from ....dependencies import nds
from ....schema import PollLogsSchema

logs_router = r = APIRouter(prefix="/logs")


@r.post("/logs/{user_id}/batch_add")
async def websocket_endpoint(user_id: str, data: PollLogsSchema):
    # TODO add proper logging
    try:
        ses = await nds._sessions.get(user_id)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"{err!r}")

    ret = 0
    try:
        ret = await ses.log_poll_data(data=data)
    except NerdDiaryError as err:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=f"{err!r}")

    return {"result": "success", "count": ret}
