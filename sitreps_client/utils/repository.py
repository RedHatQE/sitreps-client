import io
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import IO
from typing import Optional

import requests

from sitreps_client.exceptions import DownloadFailed
from sitreps_client.utils.helpers import wait_for

LOGGER = logging.getLogger(__name__)


class UnzipRepo:
    """Context Manager for Downloading and Unziping repository

    Args:
        repo_slug (str): <repo-owner>/<repo-name>
        branch (str, optional): Master branch which like to point; Defaults to "master".
        provider (str, optional): Version control tool (github/gitlab/gitlab-cce). Default "github".
        auth_token (str, optional): Authentication token for private repository.
    """

    URLS = {
        "github": "https://github.com/{repo_slug}/archive/{branch}.zip",
        "gitlab": "https://gitlab.com/{repo_slug}/-/archive/{branch}.zip",
        "gitlab-cee": "https://gitlab.cee.redhat.com/{repo_slug}/-/archive/{branch}.zip",
    }
    API_URLS = {"github": "https://api.github.com/repos/{repo_slug}/zipball/{branch}"}

    def __init__(
        self,
        repo_slug: str,
        branch: str = "master",
        provider: str = "github",
        auth_token: str = "",
    ):
        self.repo_slug = repo_slug
        self.branch = branch
        self.provider = provider
        self.auth_token = auth_token
        self.destination: Optional[tempfile.TemporaryDirectory] = None

    def download_archive(self) -> bytes:
        """Download remote repo as a zip archive."""
        if self.provider == "github" and self.auth_token:
            request_url = self.API_URLS.get("github").format(
                repo_slug=self.repo_slug, branch=self.branch
            )
            headers = {"Authorization": f"token {self.auth_token}"}
        else:
            request_url = self.URLS.get(self.provider, "").format(
                repo_slug=self.repo_slug, branch=self.branch
            )
            headers = {}

        LOGGER.info(f"Downloading.. {request_url}")

        response, err, *__ = wait_for(
            lambda: requests.get(request_url, headers=headers, verify=False),
            delay=2,
            num_sec=7,
        )
        if err or not response.ok:
            LOGGER.error(f"Fail to download archive for '{self.repo_slug}': ({response}) {err}")
            raise DownloadFailed(f"{self.repo_slug}: {str(err)}.")

        return response.content

    def unzip_archive(self, archive: IO, destination: Path) -> None:
        """Unzip the archive."""
        with zipfile.ZipFile(archive) as zip_ref:
            zip_ref.extractall(destination)
            LOGGER.info(f"Extracted '{self.repo_slug}' to '{destination}'")

    def __enter__(self) -> Path:
        """Return path of the directory with the unzipped archive."""
        archive = self.download_archive()
        self.destination = tempfile.TemporaryDirectory()
        destination_path = Path(self.destination.name)
        with io.BytesIO(archive) as archive_io:
            self.unzip_archive(archive_io, destination_path)
        return destination_path

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.destination:
            self.destination.cleanup()
        return True

    def __repr__(self):
        return (
            f"<UnzipRepo(repo_slug={self.repo_slug}, provider={self.provider},"
            f" branch={self.branch})>"
        )


if __name__ == "__main__":
    with UnzipRepo(repo_slug="RedHatInsights/patchman-engine") as dest:
        print(dest)
