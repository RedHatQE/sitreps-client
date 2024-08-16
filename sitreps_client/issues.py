"""Jira/Bugzilla issues."""

import logging
from enum import Enum
from typing import Optional
from typing import Union

from cached_property import cached_property
from jira import JIRA

from sitreps_client.exceptions import IssuesError
import time

LOGGER = logging.getLogger(__name__)


class JiraMetricsType(Enum):
    """Jira metrics type."""

    QE = "qe"
    DEV = "dev"


class JiraIssue:
    def __init__(self, url: str, token: str = None, username: str = None, password: str = None):
        self.url = url
        self.token = token
        self.username = username
        self.password = password

    @cached_property
    def client(self) -> Optional[JIRA]:
        """Note: We tried to use cache propery but facing lots of connection reset issues."""
        assert self.token or (self.username and self.password), "Need Token or Basic Auth creds."

        try:
            if self.token:
                jira_client = JIRA(
                    self.url,
                    token_auth=self.token,
                    validate=True,
                    timeout=50,
                    max_retries=5,  # don't retry to connect
                )
            else:
                jira_client = JIRA(
                    self.url, options={"verify": False}, basic_auth=(self.username, self.password)
                )
            LOGGER.debug("Jira client initialized successfully.")
            return jira_client
        # pylint: disable=broad-except
        except Exception as exc:
            msg = f"Failed to initialized Jira Client. [{str(exc)}]"
            LOGGER.error(msg)
            raise IssuesError(msg)

    def search_jql(
        self, jql_str: str, max_results: int = 5000, count: bool = True
    ) -> Optional[Union[int, list]]:
        """Return results for given JQL query.

        Args:
            jql_str: JQL query
            max_results: max number of entities.
            count: Do you want result as count or data.
        """
        try:
            data = self.client.search_issues(jql_str, maxResults=max_results, fields="id")
            if count:
                return len(data) if data else 0
            return data

        # pylint: disable=broad-except
        except Exception as exc:
            msg = f"Jira query ({jql_str}) failed with error {str(exc)}"
            LOGGER.error(msg)
            return None

    def get_issues(
        self,
        project: str,
        filters: dict,
        base_quary: str,
        custom_filter: str = None,
    ):
        base_quary = f"{base_quary} AND " if base_quary.split() else ""
        if project and custom_filter:
            query = f"{base_quary}project in ({project}) AND {custom_filter}"
        elif custom_filter:
            # If project not provided. It means that either Epic or some custom filter.
            query = f"{base_quary}{custom_filter}"
        elif project:
            query = f"{base_quary}project in ({project})"

        LOGGER.debug(f"Base Query: {query}")

        jira_stats = {}

        for key, filter in filters.items():
            jql_str = f"{query} AND {filter}"
            LOGGER.debug(f"JQL query for [{key}]: {jql_str}")
            count = self.search_jql(jql_str=jql_str)
            if count is None:
                LOGGER.error("Something bad with jql fetch... skipping jira stats.")
                return {}
            jira_stats[key] = {"count": count, "jql": jql_str}
            time.sleep(2)  # To maintain rate limit.
        return jira_stats


def get_issues(
    url: str,
    project: str,
    filters: dict,
    base_query: str = "type = Bug",
    custom_filter: str = None,
    token: str = None,
    username: str = None,
    password: str = None,
    **kwargs,
):
    LOGGER.debug(f"Collecting Jira metrics for project: {project}")
    jira = JiraIssue(url=url, token=token, username=username, password=password)
    return jira.get_issues(
        project=project,
        filters=filters,
        base_quary=base_query,
        custom_filter=custom_filter,
    )


if __name__ == "__main__":
    sitreps_jira = JiraIssue(url="https://foo.com", token="yourtoken")
