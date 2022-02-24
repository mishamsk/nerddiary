""" Report models """

from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger("nerddiary.bot.model")


class Report(BaseModel):
    name: str
