import logging

from .server import NerdDiaryServer

nds = NerdDiaryServer(logger=logging.getLogger("nerddiary.server"))
