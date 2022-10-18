"""Downloader for files on CI (Jenkins, ...)."""
import logging

import requests

from sitreps_client.exceptions import SitrepsError
from sitreps_client.utils.helpers import wait_for


LOGGER = logging.getLogger(__name__)


class CIDownloader:
    def get_text(self, url: str) -> str:
        """Return log content from the CI."""
        raise NotImplementedError


class JenkinsDownloader(CIDownloader):
    """Downloader for Jenkins."""

    def __init__(self, username: str, token: str, no_auth: bool):
        self.username = username
        self.token = token
        self.no_auth = no_auth
        self._session = None

        if not (username and token) and no_auth is False:
            raise ValueError("Username and token are needed for Jenkins auth.")

    @property
    def session(self):
        if self._session is None:
            session = requests.Session()
            if not self.no_auth:
                session.auth = (self.username, self.token)
            else:
                session.verify = False
            self._session = session
        return self._session

    def get_text(self, url: str) -> str:
        """Return log content from the Jenkins CI."""
        response, err, *__ = wait_for(lambda: self.session.get(url), delay=2, num_sec=7)

        if err:
            raise SitrepsError(str(err))

        if not response:
            raise SitrepsError(
                f'Failed to download log (status {response.status_code}) for "{url}".',
            )
        return response.text
