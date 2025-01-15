from pathlib import Path
from sitreps_client.unittests import BaseUnitTests
import pytest

BASE_PATH = Path(__file__).parent


class TestUnitTests:
    @property
    def log(self) -> str:
        """Return log data."""
        log_file = BASE_PATH / "log"
        return log_file.read_text()

    @property
    def unittest(self) -> BaseUnitTests:
        """Return instance of Base Unit tests class."""
        return BaseUnitTests()

    def get_summary(self):
        """Helper method to fetch summary from the log."""
        return self.unittest._get_test_framework_and_summary(log=self.log)

    @pytest.mark.parametrize(
        "framework, expected",
        [
            ("jest", {"total": 437, "passed": 432, "failed": 4, "skipped": 1}),
            ("cypress", {"total": 94, "passed": 91, "failed": 1, "skipped": 2}),
            ("unittest", {"total": 10, "passed": 3, "failed": 3, "skipped": 4}),
            ("pytest", {"total": 6, "passed": 2, "failed": 3, "skipped": 1}),
            ("gotest", {"total": 2, "passed": 2, "failed": 0, "skipped": 0}),
            ("rspec", {"total": 300, "passed": 285, "failed": 15, "skipped": 0}),
            ("minitest", {"total": 110, "passed": 97, "failed": 11, "skipped": 2}),
            ("busted", {"total": 18, "passed": 12, "failed": 4, "skipped": 2}),
        ],
    )
    def test_framework_summary(self, framework, expected):
        """Test different test frameworks and their results."""
        summary = self.get_summary()
        print(summary)
        # Assert framework exists in the summary
        assert framework in summary

        # Assert framework results match expected values
        assert summary[framework]["total"] == expected["total"]
        assert summary[framework]["passed"] == expected["passed"]
        assert summary[framework]["failed"] == expected["failed"]
        assert summary[framework]["skipped"] == expected["skipped"]
