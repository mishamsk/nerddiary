import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)


@pytest.fixture
def interrupt_with_sigal(capfd):
    import signal

    def _interrupt_with_sigal(func, run_time: int, signal: signal.Signals = signal.SIGINT, *args, **kwargs):
        from multiprocessing import Process
        from os import kill
        from time import sleep

        p = Process(target=func, args=args, kwargs=kwargs)
        p.start()
        sleep(run_time)
        if p.pid:
            kill(p.pid, signal)
        else:
            raise RuntimeError("Failed to run the process")

        while p.is_alive():
            sleep(0.1)

        captured = capfd.readouterr()
        return (p.exitcode, captured.out, captured.err)

    return _interrupt_with_sigal
