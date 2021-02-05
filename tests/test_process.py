"""Tests for process module."""

from loguru import logger
import pytest
from subprocess import CompletedProcess

from geohealthaccess.process import run, ProcessError

logger.disable(__name__)


class MockLogger:
    def __init__(self):
        self.output_string = None

    def info(self, output_string):
        self.output_string = output_string


@pytest.mark.parametrize(
    "args, return_code, exception_class, expected_log_output",
    [
        (("ls",), 0, None, None),  # Successful command
        (("plop",), None, OSError, None),  # File does not exist -> OSError
        (("ls boum",), None, OSError, None),  # Non-zero return code
        (
            ("ls", "setup.py",),
            0,
            None,
            "setup.py\n",
        ),  # Successful command, with logging
        (
            ("plop",),
            None,
            OSError,
            "[Errno 2] No such file or directory: 'plop'",
        ),  # File does not exist, with logging
        (
            ("ls", "boum",),
            2,
            ProcessError,
            "ls: cannot access 'boum': No such file or directory\n",
        ),
        # Non-zero return code, with logging
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
