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
    "args, return_code, exception_class, expected_log_output",
    [
        (("ls",), 0, None, None),
        (("plop",), 127, OSError, None),
        (("ls", "AUTHORS.md",), 0, None, "AUTHORS.md\n"),
        (("plop",), 127, OSError, "[Errno 2] No such file or directory: 'plop'"),
    ],
)
def test_process_run(args, return_code, exception_class, expected_log_output):
    _mock_logger = MockLogger()
    _mock_log = (
        lambda output_string: _mock_logger.info(output_string)
        if expected_log_output is not None
        else None
    )

    if exception_class is not None:
        with pytest.raises(exception_class):
            run(args, logger=_mock_log)
    else:
        completed_process = run(args, logger=_mock_log)

        assert isinstance(completed_process, CompletedProcess)
        assert completed_process.returncode == return_code

    if expected_log_output is not None:
        assert _mock_logger.output_string == expected_log_output
    else:
        assert _mock_logger.output_string is None
