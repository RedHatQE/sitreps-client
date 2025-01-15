"""Numbers of unit tests for repositories."""

import logging
import re
from pathlib import Path
from typing import Generator, Optional
from uuid import uuid4
from zipfile import ZipFile

import requests
from cached_property import cached_property
from requests.auth import AuthBase

from sitreps_client.exceptions import SitrepsError, UnitTestError
from sitreps_client.utils.ci_downloader import CIDownloader, JenkinsDownloader
from sitreps_client.utils.helpers import wait_for

LOGGER = logging.getLogger(__name__)


class TokenAuth(AuthBase):
    """Github token base authentication scheme."""

    def __init__(self, token: str):
        self.token = token

    def __call__(self, r):
        """Attach an API token to a custom auth header."""
        r.headers["Authorization"] = f"token {self.token}"
        r.headers["Accept"] = "application/vnd.github.v3+json"
        return r


class BaseUnitTests:
    """Base for UnitTests Collection."""

    def remove_ansi_escape_sequences(self, log: str) -> str:
        """Remove ANSI escape sequences from the log."""
        ansi_escape = re.compile(r"[\x1b␛]\[[0-9;]*m")
        return ansi_escape.sub("", log)

    def _get_test_framework_and_summary(self, log: str) -> dict:
        """Collect test framework and run summary info (test counts)."""
        summary = dict()
        log = self.remove_ansi_escape_sequences(log)

        summary.update(self._parse_jest(log))
        summary.update(self._parse_cypress(log))
        summary.update(self._parse_pytest(log))
        summary.update(self._parse_unittest(log))
        summary.update(self._parse_busted(log))
        summary.update(self._parse_go_test(log))
        summary.update(self._parse_rspec(log))
        summary.update(self._parse_minitest(log))

        return summary

    def _parse_jest(self, log: str) -> dict:
        """Parse Jest test framework."""
        summary = {"jest": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}

        jest_pattern = re.compile(r"Tests:\s*[^\\n]*,\s*(\d+)\s*total", re.DOTALL)
        jest_count_pattern = re.compile(r"(\d+)\s*(passed|failed|skipped|total)", re.DOTALL)

        for match in jest_pattern.finditer(log):
            result_text = match.group(0)
            for value, key in jest_count_pattern.findall(result_text):
                summary["jest"][key] += int(value)

        return summary if summary["jest"]["total"] > 0 else {}

    def _parse_cypress(self, log: str) -> dict:
        """Parse Cypress test framework."""
        summary = {}
        result_block_pattern = re.compile(r"\(Results\)[\s\S]+?(?=Spec Ran:)", re.DOTALL)
        count_pattern = re.compile(
            r"\s*(Tests|Passing|Failing|Pending|Skipped):\s*(\d+)", re.MULTILINE
        )

        if result_block_pattern.search(log):
            cypress_counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
            for result_block in result_block_pattern.finditer(log):
                result_text = result_block.group(0)

                for match in count_pattern.finditer(result_text):
                    count_type = match.group(1)
                    count_value = int(match.group(2))

                    if count_type == "Tests":
                        cypress_counts["total"] += count_value
                    elif count_type == "Passing":
                        cypress_counts["passed"] += count_value
                    elif count_type == "Failing":
                        cypress_counts["failed"] += count_value
                    elif count_type == "Skipped":
                        cypress_counts["skipped"] += count_value
                    elif count_type == "Pending":
                        cypress_counts["skipped"] += count_value
            summary["cypress"] = cypress_counts
        return summary

    def _parse_pytest(self, log: str) -> dict:
        """Parse Pytest test framework."""
        summary = {"pytest": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
        pytest_total_tests_pattern = re.compile(
            r"collected\s*(\d+)\s*items[\s\S]+?===\s*([^=]+?)\s*in\s*([\d\.]+[a-zA-Z]+)\s*==="
        )
        pytest_count_pattern = re.compile(
            r"(\d+)\s*(passed|failed|skipped|xfailed|xpassed)", re.DOTALL
        )

        if "pytest" in log or "py.test" in log:
            for match in pytest_total_tests_pattern.finditer(log):
                summary["pytest"]["total"] += int(match.group(1))

                for value, key in pytest_count_pattern.findall(match.group(2)):
                    if key == "xfailed":
                        summary["pytest"]["failed"] += int(value)
                    elif key == "xpassed":
                        summary["pytest"]["passed"] += int(value)
                    else:
                        summary["pytest"][key] += int(value)
        return summary if summary["pytest"]["total"] > 0 else {}

    def _parse_unittest(self, log: str) -> dict:
        """Parse Unittest test framework."""
        summary = {"unittest": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
        unittest_total_tests_pattern = re.compile(
            r"Ran (\d+) tests in (\d+\.\d+s|\d+s)\n+(\w+) \(([^)]+)\)"
        )
        unittest_count_pattern = re.compile(
            r"(failures|errors|skipped|expected failures)=(\d+)", re.DOTALL
        )

        for match in unittest_total_tests_pattern.finditer(log):
            summary["unittest"]["total"] += int(match.group(1))

            for key, value in unittest_count_pattern.findall(match.group(0)):
                if key == "failures":
                    summary["unittest"]["failed"] += int(value)
                if key == "errors":
                    summary["unittest"]["failed"] += int(value)
                if key == "expected failures":
                    summary["unittest"]["passed"] += int(value)
                if key == "skipped":
                    summary["unittest"]["skipped"] += int(value)

        if summary["unittest"]["total"] > 0:
            summary["unittest"]["passed"] = summary["unittest"]["total"] - (
                summary["unittest"]["failed"] + summary["unittest"]["skipped"]
            )
            return summary
        return {}

    def _parse_busted(self, log: str) -> dict:
        """Parse Busted test framework."""
        summary = {"busted": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
        busted_count_pattern = re.compile(
            r"(\d+) success(es?)? \/ (\d+) failures? \/ (\d*) errors? \/ (\d*) pending :"
            r" (\d+\.\d+) seconds",
            re.DOTALL,
        )

        for match in busted_count_pattern.finditer(log):
            summary["busted"]["passed"] += int(match.group(1))
            summary["busted"]["failed"] += int(match.group(3))
            summary["busted"]["failed"] += int(match.group(4))  # error
            summary["busted"]["skipped"] += int(match.group(5))
        summary["busted"]["total"] = sum(summary["busted"].values())
        return summary if summary["busted"]["total"] > 0 else {}

    def _parse_go_test(self, log: str) -> dict:
        """Parse Go test framework."""
        summary = {}
        go_count_pattern = re.compile(r"=== RUN\s+(\S+)[\s\S]+?---\s+(PASS|FAIL|SKIP)", re.DOTALL)
        if go_count_pattern.search(log):
            go_counts = {"passed": 0, "failed": 0, "skipped": 0}
            for _, key in go_count_pattern.findall(log):
                if key == "PASS":
                    go_counts["passed"] += 1
                if key == "FAIL":
                    go_counts["failed"] += 1
                if key == "SKIP":
                    go_counts["skipped"] += 1
            go_counts["total"] = sum(go_counts.values())
            summary["gotest"] = go_counts
        return summary

    def _parse_rspec(self, log: str) -> dict:
        """Parse RSpec test framework.

        https://rspec.info/
        """
        summary = {"rspec": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}

        # Pattern to capture total examples and failures
        rspec_detect_pattern = re.compile(r"(\d+)\s*examples,\s*(\d+)\s*failures", re.DOTALL)

        if rspec_detect_pattern.search(log):  # Flag to detect RSpec output
            for total, failed in rspec_detect_pattern.findall(log):
                passed = int(total) - int(failed)  # Assuming passed = total - failed

                # Accumulate the counts
                summary["rspec"]["total"] += int(total)
                summary["rspec"]["failed"] += int(failed)
                summary["rspec"]["passed"] += passed
        return summary if summary["rspec"]["total"] > 0 else {}

    def _parse_minitest(self, log: str) -> dict:
        """Parse Minitest test framework."""
        summary = {"minitest": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}

        # Pattern to capture test results: total, failures, errors, skips
        minitest_count_pattern = re.compile(
            r"(\d+) tests, (\d+) assertions, (\d+) failures, (\d+) errors, (\d+) skips", re.DOTALL
        )
        # Check for Minitest by detecting "rake test" or "run options --seed"
        if ("rake test" in log or "run options --seed" in log) and minitest_count_pattern.search(
            log
        ):
            for match in minitest_count_pattern.finditer(log):
                tests = int(match.group(1))
                failures_errors = int(match.group(3)) + int(match.group(4))
                skips = int(match.group(5))
                passed = tests - (failures_errors + skips)
                summary["minitest"]["total"] += tests
                summary["minitest"]["failed"] += failures_errors
                summary["minitest"]["skipped"] += skips
                summary["minitest"]["passed"] += passed
        return summary if summary["minitest"]["total"] > 0 else {}

    def combine_summary_data(self, data: list) -> list[dict]:
        """Combine collected data from different frameworks into a unified summary."""
        combined_data = {}
        for entry in data:
            for framework, counts in entry.items():
                if framework not in combined_data:
                    combined_data[framework] = {key: value for key, value in counts.items()}
                else:
                    for key, value in counts.items():
                        combined_data[framework][key] += value
        return [
            {**summary, "framework_name": framework} for framework, summary in combined_data.items()
        ]


class GHActionUnitTests(BaseUnitTests):
    """Test summary from GitHub Actions."""

    GH_ACTION_BASE_API = "https://api.github.com/repos"
    GH_ACTION_RUNS = GH_ACTION_BASE_API + "/{repo_slug}/actions/runs"

    def __init__(self, repo_slug: str, github_token: str, branch: str, workflow: str = None):
        self.repo_slug = repo_slug
        self.branch = branch
        self.workflow = workflow
        self.github_token = github_token
        self._auth = TokenAuth(self.github_token)

    def get_runs(self):
        """Get GitHub Actions runs for repo."""
        response, err, *__ = wait_for(
            lambda: requests.get(
                self.GH_ACTION_RUNS.format(repo_slug=self.repo_slug),
                params={
                    "branch": self.branch,
                    "conclusion": "success",
                    "exclude_pull_requests": "true",
                    "per_page": 75,
                },
                auth=self._auth,
            ),
            delay=2,
            num_sec=3,
            ignore_falsy=True,
        )

        if not response.ok:
            LOGGER.error(f"[GhAction-{self.repo_slug}]: Unable to fetch runs: {response.reason}")
            raise SitrepsError(f"Unable to fetch runs: {response.reason}")

        data = response.json()
        runs = data.get("workflow_runs")
        if not runs:
            LOGGER.warning(
                f"[GhAction-{self.repo_slug}]: No runs found for '{self.repo_slug}' "
                f"on branch '{self.branch}'."
            )
        if self.workflow:
            runs = [run for run in runs if self.workflow in run["name"]]
            if not runs:
                LOGGER.warning(
                    f"[GhAction-{self.repo_slug}]: No runs found for workflow name {self.workflow}."
                )
        else:
            runs = [run for run in runs if "test" in run["name"].lower()]
        return runs

    def get_logs(self) -> list:
        """Get logs for the latest workflow run."""
        logs = []

        runs = self.get_runs()
        if not runs:
            return logs
        run = runs[0]
        LOGGER.info(f"[GhAction-{self.repo_slug}]: Latest run: {run['html_url']}")
        response, err, *__ = wait_for(
            lambda: requests.get(runs[0]["logs_url"], auth=TokenAuth(self.github_token)),
            delay=2,
            num_sec=7,
        )
        if not response.ok:
            LOGGER.error(f"[GhAction-{self.repo_slug}]: Unable to fetch logs {response.reason}")
            raise SitrepsError(f"Unable to fetch logs: {response.reason}")

        zipfile_name = Path(f"/tmp/github_action_log_{uuid4()}.zip")

        with open(zipfile_name, "wb") as f:
            f.write(response.content)

        with ZipFile(zipfile_name) as zip_log:
            logfiles = [x for x in zip_log.infolist() if "/" not in x.filename]
            logs = [zip_log.read(log) for log in logfiles]

        if zipfile_name.exists():
            zipfile_name.unlink()
        return logs

    def get_tests_summary(self) -> Optional[list[dict]]:
        """Return number of unit tests."""
        logs = self.get_logs()

        if not logs:
            LOGGER.warning(f"[GhAction-{self.repo_slug}]: No logs/runs collected.")
            return None

        data = [self._get_test_framework_and_summary(log.decode()) for log in logs]
        return self.combine_summary_data(data=data)

    def __repr__(self):
        return f"<GHActionUnitTests(repo_slug={self.repo_slug})>"


class TravisUnitTests(BaseUnitTests):
    """Number of unit tests from Travis."""

    TRAVIS_PRIVATE = "https://app.travis-ci.com"
    TRAVIS_API_PRIVATE = "https://api.travis-ci.com"
    TRAVIS_PUBLIC = "https://app.travis-ci.org"
    TRAVIS_API_PUBLIC = "https://api.travis-ci.org"

    def __init__(
        self,
        repo_slug: str,
        access_token: str = None,
        branch: str = "main",
        is_private: bool = True,
    ):
        self.repo_slug = repo_slug
        self.access_token = access_token
        self.branch = branch
        self.is_private = is_private

    @cached_property
    def session(self):
        session = requests.Session()
        headers = {"Authorization": f"token {self.access_token}"} if self.is_private else {}
        session.headers.update(headers)
        return session

    @cached_property
    def ui_base_url(self):
        return self.TRAVIS_PRIVATE if self.is_private else self.TRAVIS_PUBLIC

    @cached_property
    def api_base_url(self):
        return self.TRAVIS_API_PRIVATE if self.is_private else self.TRAVIS_API_PUBLIC

    def get_jobs(self) -> list:
        branch_url = f"{self.api_base_url}/repos/{self.repo_slug}/branches/{self.branch}"
        response = self.session.get(branch_url)
        response.raise_for_status()
        data = response.json()
        job_ids = data.get("branch", {}).get("job_ids", [])
        return job_ids

    def get_log_for_job(self, job_id) -> str:
        log_url = f"{self.api_base_url}/v3/job/{job_id}/log.txt"
        LOGGER.info(f"{self.ui_base_url}/github/{self.repo_slug}/jobs/{job_id}")
        response = self.session.get(log_url)
        if response.status_code == 403 and response.json()["error_type"] == "log_expired":
            LOGGER.warning(f"Log expired for {response.url}")
            return " "
        response.raise_for_status()
        return response.text

    def get_logs(self) -> Generator[str, None, None]:
        for job_id in self.get_jobs():
            try:
                log = self.get_log_for_job(job_id)
            except UnitTestError as e:
                raise SitrepsError(f"[Travis-{self.repo_slug}]: {e}")
            yield log

    def get_tests_summary(self) -> Optional[list[dict]]:
        """Return number of unit tests."""
        data = []
        try:
            log_generator = self.get_logs()
        # pylint: disable=broad-except
        except Exception as exc:
            msg = f"[Travis-{self.repo_slug}]: {exc}"
            LOGGER.error(msg)
            return None
        for ci_log in log_generator:
            data.append(self._get_test_framework_and_summary(ci_log))
        return self.combine_summary_data(data=data)

    def __repr__(self):
        return f"<TravisUnitTests(repo_slug={self.repo_slug})>"


class CIUnitTests(BaseUnitTests):
    """Number of unit tests from CI."""

    def __init__(self, url: str, ci_downloader: CIDownloader):
        self.url = url
        self.ci_downloader = ci_downloader

    def get_tests_summary(self) -> Optional[list[dict]]:
        try:
            string = self.ci_downloader.get_text(self.url)
        # pylint: disable=broad-except
        except Exception as exc:
            LOGGER.warning('Skipping tests count for "%s", failure: %s', self.url, str(exc))
            return None
        if summary := self._get_test_framework_and_summary(string):
            return self.combine_summary_data([summary])

    def __repr__(self):
        return f"<CIUnitTests(url={self.url})>"


class UnitTestFactory:
    """Factory to create the appropriate UnitTest object based on the configuration."""

    @staticmethod
    def create(ci_name: str, config: dict[str, str | None]):
        """Factory method to create the correct CIUnitTests object based on configuration."""
        if ci_name == "travis":
            return TravisUnitTests(
                repo_slug=config.get("repo_slug"),
                branch=config.get("branch", "main"),
                access_token=config.get("access_token"),
            )
        elif ci_name == "gh_action":
            return GHActionUnitTests(
                repo_slug=config.get("repo_slug"),
                branch=config.get("branch", "master"),
                github_token=config.get("token"),
                workflow=config.get("workflow"),
            )
        elif ci_name == "jenkins":
            jenkins_downloader = JenkinsDownloader(
                username=config.get("username", ""),
                token=config.get("token", ""),
                no_auth=config.get("no_auth", False),
            )
            return CIUnitTests(
                url=config.get("url"),
                ci_downloader=jenkins_downloader,
            )
        else:
            raise ValueError(f"Unsupported CI name: {ci_name}")


def get_unit_tests(configs: dict) -> Optional[list[dict]]:
    """
    Collect unit test summaries from different CI platforms.

    Arguments:
        configs: A dictionary where the key is the CI platform (e.g., "travis", "gh_action")
                 and the value is another dictionary with configuration options for that platform.

    Returns:
        A dictionary containing the unit test summaries from each CI platform.
    """
    ci_name = configs.get("ci_name")
    repo_slug = configs.get("config", {}).get("repo_slug")

    try:
        # Use factory to create CI-specific unit test objects
        ci_instance = UnitTestFactory.create(**configs)
        summary = ci_instance.get_tests_summary()
        unittest_data = [
            {**item_summary, "ci_name": ci_name, "repo_slug": repo_slug} for item_summary in summary
        ]
        return unittest_data

    except Exception as e:
        # Handle errors gracefully and store empty data
        LOGGER.error(f"Error collecting unit tests for : {e}")
        # unit_tests[ci_name] = {}
