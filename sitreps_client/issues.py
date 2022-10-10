"""Jira/Bugzilla issues."""
import logging
from typing import Optional
from typing import Union

from cached_property import cached_property
from jira import JIRA

from sitreps_client.exceptions import IssuesError


LOGGER = logging.getLogger(__name__)


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
                    timeout=30,
                    max_retries=5,  # don't retry to connect
                )
            else:
                jira_client = JIRA(
                    self.url, options={"verify": False}, basic_auth=(self.username, self.password)
                )
            LOGGER.info("Jira client initialized successfully.")
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
            data = self.client.search_issues(jql_str, maxResults=max_results)
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
        type: str = "Bug",
        base_query: str = 'project = "{project}" AND type = {type}',
        custom_filter: str = None,
    ):
        base_query = base_query.format(project=project, type=type)
        LOGGER.debug(f"Base Query: {base_query}")

        if custom_filter:
            LOGGER.debug(f"Found custom filter: {custom_filter}")
            base_query = f"{base_query} AND {custom_filter}"

        jira_stats = {}
        for key, filter in filters.items():
            jql_str = f"{base_query} AND {filter}"
            LOGGER.debug(f"JQL query for [{key}]: {jql_str}")
            jira_stats[key] = {"count": self.search_jql(jql_str=jql_str), "jql": jql_str}

        return jira_stats


def get_issues(
    url: str,
    project: str,
    filters: dict,
    type: str = "Bug",
    base_query: str = 'project = "{project}" AND type = {type}',
    custom_filter: str = None,
    token: str = None,
    username: str = None,
    password: str = None,
    **kwargs,
):
    LOGGER.info(f"Collecting Jira metrics for project: {project}")
    jira = JiraIssue(url=url, token=token, username=username, password=password)
    return jira.get_issues(
        project=project,
        filters=filters,
        type=type,
        base_query=base_query,
        custom_filter=custom_filter,
    )


if __name__ == "__main__":
    sitreps_jira = JiraIssue(url="https://foo.com", token="yourtoken")
