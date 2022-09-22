"""Jira/Bugzilla issues."""
import logging
from typing import Optional

from cached_property import cached_property
from jira import JIRA

from sitreps_client.exceptions import IssuesError


LOGGER = logging.getLogger(__name__)


class JiraIssue:
    def __init__(
        self, url: str = "", token: str = "", username: str = "", password: str = ""
    ) -> None:
        self.url = url
        self.token = token
        self.username = username
        self.password = password
        _auth_check = self.token or (self.username and self.password)
        assert _auth_check, "Please provide Token or Basic auth for authentication."

    @cached_property
    def client(self) -> Optional[JIRA]:
        """Note: We tried to use cache propery but facing lots of connection reset issues."""
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
    ) -> Optional[int]:
        """Return results for given JQL query.
        Args:
            jql_str: JQL query
            max_results: max number of entities.
            count: Do you want result as count or data.
        """
        try:
            data = self.client.search_issues(jql_str, maxResults=max_results)
            if not count:
                return data
            if data:
                return len(data)
            else:
                return 0
        # pylint: disable=broad-except
        except Exception as exc:
            msg = f"Jira query ({jql_str}) failed with error {str(exc)}"
            LOGGER.error(msg)
            return None

    def get_issues(self, project: str, type: str = "Bug", jira_queries_conf: dict = None):
        query_base = f'project = "{project}" AND type = {type}'
        print(f"Jira base quary: {query_base}")
        # if jira_query_append:
        #     query_base = f"{query_base} AND {jira_query_append}"
        #     print(f"Appended quary from user {query_base}")

        jira_stats = {
            "all_resolved": self.search_jql(f"{query_base} AND resolution != Unresolved"),
            "all_unresolved": self.search_jql(f"{query_base} AND resolution = Unresolved"),
            "todo": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                '("To Do", Backlog, "Back Log", FAILED_QA, "Failed QA")',
            ),
            "on_qa": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                '(ON_QA, "On QA", Verification)',
            ),
            "code_review": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                f'(CODE_REVIEW, "Code Review")',
            ),
            "blocked": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                '(BLOCK, Blocked, "Blocked/On Hold", "Blocked / Stalled", "Blocked External")',
            ),
            "rejected": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                '(Rejected, Abandoned, "Rejected from customer")',
            ),
            "in_progress": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                f'("In Progress", "In Development")',
            ),
            "created_last_month": self.search_jql(f'{query_base} AND createdDate >= "-30d"'),
            "resolved_last_month": self.search_jql(f'{query_base} AND resolutiondate >= "-30d"'),
            "todo_older_than_60d": self.search_jql(
                f"{query_base} AND resolution = Unresolved AND status in "
                '("To Do", Backlog, "Back Log", FAILED_QA, "Failed QA") '
                'AND createdDate < "-60d"',
            ),
        }
        return jira_stats


if __name__ == "__main__":
    sitreps_jira = JiraIssue(url="https://foo.com", token="yourtoken")
    stats = sitreps_jira.get_issues(project="SPM")
    print(stats)
