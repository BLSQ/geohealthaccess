"""Tests for process module."""

from loguru import logger
import pytest
from subprocess import CompletedProcess

from geohealthaccess.process import run

logger.disable(__name__)


class MockLogger:
    def __init__(self):
        self.output_string = None

    def info(self, output_string):
        self.output_string = output_string


@pytest.mark.parametrize(
    "command, return_code, exception_class, log",
    [
        ("ls", 0, None, False),
        ("kapoué", 127, OSError, False),
        ("ls", 0, None, True),
        ("kapoué", 127, OSError, True),
    ],
)
def test_process_run(command, return_code, exception_class, log):
    _mock_logger = MockLogger()
    _mock_log = (
        lambda output_string: _mock_logger.info(output_string) if log is True else None
    )

    if exception_class is not None:
        with pytest.raises(exception_class):
            run(command, logger=_mock_log)
    else:
        completed_process = run(command, logger=_mock_log)

        assert isinstance(completed_process, CompletedProcess)
        assert completed_process.returncode == return_code

        log_assertion = (
            _mock_logger.output_string is not None
            if log
            else _mock_logger.output_string is None
        )
        assert log_assertion
