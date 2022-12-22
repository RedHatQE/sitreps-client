"""Numbers of unit tests for repositories."""
import logging
import re
from pathlib import Path
from typing import Generator
from typing import Optional
from uuid import uuid4
from zipfile import ZipFile

import requests
from cached_property import cached_property
from PyTravisCI import TravisCI
from PyTravisCI.defaults.access_points import OPEN
from PyTravisCI.defaults.access_points import PRIVATE
from PyTravisCI.exceptions import TravisCIError
from requests.auth import AuthBase

from sitreps_client.exceptions import SitrepsError
from sitreps_client.utils.ci_downloader import CIDownloader
from sitreps_client.utils.ci_downloader import JenkinsDownloader
from sitreps_client.utils.helpers import escape_ansi

LOGGER = logging.getLogger(__name__)

KNOWN_TESTING_TOOLS = ("gotest", "pytest", "pyunittest", "npm", "rake", "maven", "junit", "other")


class TokenAuth(AuthBase):
    """Github token base authentication scheme."""

    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        """Attach an API token to a custom auth header."""
        r.headers["Authorization"] = f"token {self.token}"
        r.headers["Accept"] = "application/vnd.github.v3+json"
        return r


class BaseUnitTests:
    """Base for UnitTests Collection."""

    @staticmethod
    def _get_testing_tools(ci_log: str):
        """Collect UnitTest tools."""
        tools_found = []
        ci_log = escape_ansi(ci_log)
        LOGGER.info("[UnitTests]: Collecting unit test tools...")

        for line in ci_log.splitlines():
            if "=== RUN " in line:
                tools_found.append("gotest")
            if "pytest" in line or "py.test" in line:
                tools_found.append("pytest")
            if "Ran " in line and " tests in " in line:
                tools_found.append("pyunittest")
            if "Suite duration: " in line and " Tests: " in line:
                tools_found.append("other")
            if "npm" in line or "yarn test" in line:
                tools_found.append("npm")
            if "rake " in line and "validate" in line:
                tools_found.append("rake")
            if "maven" in line:
                tools_found.append("maven")

        tools_found = set(tools_found)

        if len(tools_found) > 1:
            LOGGER.warning(
                f"[UnitTests]: Multiple testing tools detected ({tools_found}),"
                f"You can set specific in setting like 'test_tool: pytest'."
                f"Known testing tools are {KNOWN_TESTING_TOOLS}."
            )
        if len(tools_found) == 0:
            LOGGER.warning("[UnitTests]: No testing tool detected.")

        return tools_found

    def _get_tests_count(self, ci_log: str, test_tool: Optional[str] = None) -> int:  # noqa: C901
        """Identify number of unit tests from the CI log.

        Try to parse output of various unit testing tools (pytest, rake, etc.).

        Args:
            ci_log (str): Decoded CI log
            test_tool (str): Comma separated tools. If not provided it will try to fetch from log.
        """
        # pylint: disable=too-many-branches
        tests_count = 0

        if test_tool:
            tools = test_tool.split(",")
        else:
            tools = self._get_testing_tools(ci_log)

        LOGGER.info(f"[UnitTests]: testing tools: {tools}")

        for line in escape_ansi(ci_log).splitlines():
            # At this point all test run already completed.
            if "https://codecov.io/upload" in line or "bonfire deploy-iqe-cji" in line:
                break

            # golang
            if "gotest" in tools and "=== RUN " in line:
                LOGGER.debug(f"gotest: {line}")
                tests_count += 1
                continue

            # pytest
            if "pytest" in tools and "collected " in line and " items" in line:
                LOGGER.debug(f"pytest: {line}")
                try:
                    tests_count += int(
                        re.search("collected ([0-9]+) items", line).group(1)  # type: ignore
                    )
                except (IndexError, AttributeError):
                    pass
                continue

            # python unit tests
            if "pyunittest" in tools and "Ran " in line and " tests in " in line:
                LOGGER.debug(f"pyunittest: {line}")
                try:
                    tests_count += int(
                        re.search("Ran ([0-9]+) tests in", line).group(1)  # type: ignore
                    )
                except (IndexError, AttributeError):
                    pass
                continue

            # javascript; npm/yarn
            if "npm" in tools and "Tests:" in line and " total" in line:
                LOGGER.debug(f"npm: {line}")
                try:
                    tests_count += int(
                        re.search("Tests:.+, ([0-9]+) total", line).group(1)  # type: ignore
                    )
                except (IndexError, AttributeError):
                    pass
                continue

            # rake validate
            if "rake" in tools and all(exp in line for exp in ("tests", "assertions", "failures")):
                LOGGER.debug(f"rake: {line}")
                try:
                    tests_count += int(re.search("([0-9]+) tests,", line).group(1))  # type: ignore
                except (IndexError, AttributeError):
                    pass
                continue

            # maven java unit test
            if "maven" in tools and all(
                exp in line for exp in ("Tests run", "Failures", "Errors", "Skipped")
            ):
                LOGGER.debug(f"maven: {line}")
                try:
                    tests_count += int(re.search("Tests run: ([0-9]+),", line).group(1))
                except (IndexError, AttributeError):
                    pass
                continue

            # junit
            if "junit" in tools and "Executed " in line and " tests" in line:
                LOGGER.debug(f"junit: {line}")
                try:
                    tests_count += int(
                        re.search("Executed ([0-9]+) tests", line).group(1)  # type: ignore
                    )
                except (IndexError, AttributeError):
                    pass
                break

            # ??
            if "other" in tools and "Suite duration: " in line and " Tests: " in line:
                LOGGER.debug(f"other: {line}")
                try:
                    tests_count += int(re.search("Tests: ([0-9]+)", line).group(1))  # type: ignore
                except (IndexError, AttributeError):
                    pass
                continue

        return tests_count


class GHActionUnitTests(BaseUnitTests):
    """Number of unit tests from Github Actions."""

    GH_ACTION_BASE_API = "https://api.github.com/repos"
    GH_ACTION_RUNS = GH_ACTION_BASE_API + "/{repo_slug}/actions/runs"

    def __init__(
        self,
        repo_slug: str,
        github_token: str,
        branch: str = "master",
        workflow: str = None,
        test_tool: str = None,
    ):
        self.repo_slug = repo_slug
        self.branch = branch
        self.github_token = github_token
        self.workflow = workflow
        self.test_tool = test_tool
        self._auth = TokenAuth(self.github_token)

    def get_runs(self):
        """Get github actions runs for repo."""
        resp = requests.get(
            self.GH_ACTION_RUNS.format(repo_slug=self.repo_slug),
            params={
                "branch": self.branch,
                "conclusion": "success",
                "exclude_pull_requests": "true",
                "per_page": 75,
            },
            auth=self._auth,
        )
        if not resp.ok:
            LOGGER.error(f"[GhAction-{self.repo_slug}]: Unable to fetch runs: {resp.reason}")
            raise SitrepsError(f"Unable to fetch runs: {resp.reason}")

        data = resp.json()
        runs = data.get("workflow_runs")
        if not runs:
            LOGGER.warning(
                f"[GhAction-{self.repo_slug}]: runs not found for '{self.repo_slug}' against"
                f" '{self.branch}' branch."
            )
        if self.workflow:
            runs = [run for run in runs if run["name"] == self.workflow]
            if not runs:
                LOGGER.warning(
                    f"[GhAction-{self.repo_slug}]: "
                    f"runs not found with workflow name {self.workflow}."
                )
        else:
            runs = [run for run in runs if "test" in run["name"].lower()]
        return runs

    def get_logs(self):
        """Get logs for the latest workflow run."""
        logs = []  # can be multiple as github action store in multiple files.

        runs = self.get_runs()
        if not runs:
            return logs
        run = runs[0]  # select first one
        LOGGER.info(f"[GhAction-{self.repo_slug}]: Latest run: {run['html_url']}")
        resp = requests.get(runs[0]["logs_url"], auth=TokenAuth(self.github_token))
        if not resp.ok:
            LOGGER.error(f"[GhAction-{self.repo_slug}]: Unable to fetch logs {resp.reason}")
            raise SitrepsError(f"Unable to fetch logs: {resp.reason}")

        zipfile_name = Path(f"/tmp/github_action_log_{uuid4()}.zip")

        with open(zipfile_name, "wb") as f:
            f.write(resp.content)

        with ZipFile(zipfile_name) as zip_log:
            logfiles = [x for x in zip_log.infolist() if "/" not in x.filename]
            logs = [zip_log.read(log) for log in logfiles]
        return logs

    def get_num_of_tests(self) -> Optional[int]:
        """Return number of unit tests."""
        logs = self.get_logs()

        if not logs:
            LOGGER.warning(f"[GhAction-{self.repo_slug}]: No logs/runs collected.")
            return 0

        return sum(self._get_tests_count(log.decode(), test_tool=self.test_tool) for log in logs)

    def __repr__(self):
        return f"<GHActionUnitTests(repo_slug={self.repo_slug})>"


class TravisUnitTests(BaseUnitTests):
    """Number of unit tests from Travis."""

    def __init__(
        self,
        repo_slug: str,
        access_token: str = None,
        branch: str = "master",
        is_private: bool = True,
        test_tool: str = None,
    ):
        self.repo_slug = repo_slug
        self.access_token = access_token
        self.branch = branch
        self.is_private = is_private
        self.test_tool = test_tool

    @cached_property
    def client(self):
        """Travis client.

        Returns: TravisCI object
        """
        if self.access_token:
            access_point = PRIVATE if self.is_private else OPEN
            return TravisCI(access_token=self.access_token, access_point=access_point)
        return TravisCI()

    def get_logs(self) -> Generator[str, None, None]:
        try:
            repo = self.client.get_repository(repository_id_or_slug=self.repo_slug)
        except Exception as e:
            msg = f"[Travis-{self.repo_slug}]: is it using private travis? is repo used travis?"
            LOGGER.warning(msg)
            raise SitrepsError(f"{msg}, Error:{e}")

        builds = repo.get_builds(params={"branch.name": self.branch, "state": "passed", "limit": 1})

        if not builds:
            raise SitrepsError(
                f"[Travis-{self.repo_slug}]: Build for branch '{self.branch}' with passed status "
                f"not found."
            )
        build = builds[0]  # Select first build i.e. latest one.
        LOGGER.info(f"[Travis-{self.repo_slug}]: Latest build: {build.id}")
        jobs = build.get_jobs().jobs
        test_jobs = [job for job in jobs if job.stage and "test" in job.stage.name.lower()]
        if test_jobs:
            LOGGER.info(f"[Travis-{self.repo_slug}]: Test jobs detected. Limiting scan.")
            jobs = test_jobs

        for job in jobs:
            try:
                log = job.get_log()
            except TravisCIError as e:
                raise SitrepsError(f"[Travis-{self.repo_slug}]: {e}")
            yield log.content

    def get_num_of_tests(self) -> Optional[int]:
        """Return number of unit tests."""
        try:
            log_generator = self.get_logs()
        # pylint: disable=broad-except
        except Exception as exc:
            msg = f"[Travis-{self.repo_slug}]: {exc}"
            LOGGER.error(msg)
            return None

        for ci_log in log_generator:
            num_of_tests = self._get_tests_count(ci_log, test_tool=self.test_tool)
            if num_of_tests > 0:
                return num_of_tests
        return 0

    def __repr__(self):
        return f"<TravisUnitTests(repo_slug={self.repo_slug})>"


class CIUnitTests(BaseUnitTests):
    """Number of unit tests from CI."""

    def __init__(self, url: str, ci_downloader: CIDownloader, test_tool: str = None):
        self.url = url
        self.ci_downloader = ci_downloader
        self.test_tool = test_tool

    def get_num_of_tests(self) -> Optional[int]:
        """Return number of unit tests."""
        try:
            string = self.ci_downloader.get_text(self.url)
        # pylint: disable=broad-except
        except Exception as exc:
            LOGGER.warning('Skipping tests count for "%s", failure: %s', self.url, str(exc))
            return None
        num_of_tests = self._get_tests_count(string, test_tool=self.test_tool)
        return num_of_tests

    def __repr__(self):
        return f"<CIUnitTests(url={self.url})>"


def get_unit_tests(travis=None, gh_action=None, jenkins=None):
    unit_tests = {}

    if travis:
        LOGGER.info(f"[UnitTests-{travis.get('repo_slug')}]: Collecting with 'travis'.")
        unit_tests["travis"] = TravisUnitTests(
            repo_slug=travis.get("repo_slug"),
            branch=travis.get("branch"),
            access_token=travis.get("access_token"),
            test_tool=travis.get("test_tool"),
        )

    if gh_action:
        LOGGER.info(f"[UnitTests-{gh_action.get('repo_slug')}]: Collecting with 'gh_actions'.")
        unit_tests["gh_action"] = GHActionUnitTests(
            repo_slug=gh_action.get("repo_slug"),
            branch=gh_action.get("branch"),
            github_token=gh_action.get("token"),
            workflow=gh_action.get("workflow"),
            test_tool=gh_action.get("test_tool"),
        )

    if jenkins:
        LOGGER.info("[UnitTests]: Collecting with 'jenkins'.")
        jenkins_downloader = JenkinsDownloader(
            username=jenkins.get("username", ""),
            token=jenkins.get("token", ""),
            no_auth=jenkins.get("no_auth", False),
        )
        unit_tests["jenkins"] = CIUnitTests(
            url=jenkins.get("url"),
            ci_downloader=jenkins_downloader,
            test_tool=jenkins.get("test_tool"),
        )

    for key, ci in unit_tests.items():
        try:
            unit_tests[key] = ci.get_num_of_tests()
        except SitrepsError as e:
            unit_tests[key] = 0
            LOGGER.error(f"{e}")
    return unit_tests
