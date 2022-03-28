import logging
import signal

SIGNAL_TRANSLATION_MAP = {
    signal.SIGINT: "SIGINT",
}


class DelayedKeyboardInterrupt:
    def __init__(self, logger: logging.Logger = logging.getLogger("delayedkeyboardinterrupt")):
        """
        Constructs a context manager that suppresses SIGINT signal handlers for a block of code.
        The signal handlers are called on exit from the block.
        """
        self._sig = None
        self._frame = None
        self._old_signal_handler_map = None
        self._logger = logger

    def __enter__(self):
        self._logger.debug("Entering DelayedKeyboardInterrupt context")
        self._old_signal_handler_map = {
            sig: signal.signal(sig, self._handler) for sig, _ in SIGNAL_TRANSLATION_MAP.items()
        }

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._logger.debug("Exiting DelayedKeyboardInterrupt context. Restoring signal handlers")
        for sig, handler in self._old_signal_handler_map.items():
            signal.signal(sig, handler)

        if self._sig is None:
            return

        self._logger.debug(f"Exiting DelayedKeyboardInterrupt context. Handling {SIGNAL_TRANSLATION_MAP[self._sig]}")

        try:
            self._old_signal_handler_map[self._sig](self._sig, self._frame)  # type:ignore
        except TypeError:
            pass

    def _handler(self, sig, frame):
        self._sig = sig
        self._frame = frame

        self._logger.debug(f"DelayedKeyboardInterrupt._handler: {SIGNAL_TRANSLATION_MAP[sig]} received; delaying")
