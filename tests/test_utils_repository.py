import pytest

from sitreps_client.exceptions import DownloadFailed
from sitreps_client.utils.repository import UnzipRepo


def test_unziprepo():
    with UnzipRepo(repo_slug="RedHatInsights/patchman-engine") as dest:
        assert dest


def test_unziprepo_download_fail():
    with pytest.raises(DownloadFailed):
        with UnzipRepo(repo_slug="RedHatInsights/foobar") as dest:
            assert dest
