import signal
from time import sleep

from nerddiary.asynctools.delayedsignal import DelayedKeyboardInterrupt


def run():
    with DelayedKeyboardInterrupt():
        sleep(1)
        print("Ok")


def test_sigint_same_process(interrupt_with_sigal):
    exitcode, out, err = interrupt_with_sigal(run, 0.5, signal.SIGINT)
    assert exitcode == 1 and out == "Ok\n" and err.endswith("KeyboardInterrupt\n")
