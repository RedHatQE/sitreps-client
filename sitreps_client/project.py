from pathlib import Path

from attr import define
from attr import field
from box import Box

from sitreps_client.cloc import get_cloc as _get_cloc
from sitreps_client.code_coverage import get_code_coverage as _get_code_coverage
from sitreps_client.issues import get_issues as _get_issues
from sitreps_client.utils.helpers import load_file
from sitreps_client.utils.helpers import merge_dicts
from sitreps_client.utils.path import CONF_PATH

SUPPORTED_HOSTS = ("github", "gitlab-cee", "gitlab")
SUPPORTED_CLOC_ARGS = {"suffix", "folders_to_skip", "names_to_skip", "exclude_tests", "auth_token"}
SUPPORTED_UNITTEST_ARGS = {"travis", "github_action", "jenkins"}
SUPPORTED_SONARQUBE_ARGS = {"project_id", "host", "token"}


@define
class ProjectGroup:
    """Project Group (bundle) which hold different Projects (components)."""

    name: str
    title: str = field(repr=False)
    projects: list = field(default=[], repr=False)


@define
class Repository:
    """Project repository."""

    title: str
    url: str
    branch: str = "master"
    type: str = "test"
    _cloc: dict = field(default={}, repr=False)
    _sonarqube: dict = field(default={}, repr=False)
    _unit_tests: dict = field(default={}, repr=False)

    @_cloc.validator
    def _val_cloc(self, attribute, value):
        if value and not set(value.keys()).issubset(SUPPORTED_CLOC_ARGS):
            raise ValueError(f"Supported cloc params are: {SUPPORTED_CLOC_ARGS}")

    @_sonarqube.validator
    def _val_sonar(self, attribute, value):
        if value and not set(value.keys()).issubset(SUPPORTED_SONARQUBE_ARGS):
            raise ValueError(f"Supported cloc params are: {SUPPORTED_SONARQUBE_ARGS}")

    @_unit_tests.validator
    def _val_unit_test(self, attribute, value):
        if value and not set(value.keys()).issubset(SUPPORTED_UNITTEST_ARGS):
            raise ValueError(f"Supported cloc params are: {SUPPORTED_UNITTEST_ARGS}")

    @classmethod
    def from_config(cls, rep_conf):
        return cls(**rep_conf)

    @property
    def repo_slug(self):
        """Return repo-slug of repository."""
        url = self.url.rstrip("/")
        components = url.split("/")
        return "/".join(components[-2:])

    @property
    def name(self):
        """Return name of repository."""
        return self.repo_slug.split("/")[-1]

    @property
    def provider(self):
        """Return host of repository ["github", "gitlab-cee" ,"gitlab"]."""
        for _host in SUPPORTED_HOSTS:
            if _host.replace("-", ".") in self.url:
                return _host
        raise ValueError(f"'{self.url}' not supported url. Sitreps only support {SUPPORTED_HOSTS}")

    def get_cloc(self, local_path=None):
        """Get CLOC of repository.
        Args:
            local_path: local path else it will download repository.
        """
        return _get_cloc(
            path=local_path,
            repo_slug=self.repo_slug,
            provider=self.provider,
            branch=self.branch,
            auth_token=self._cloc.get("auth_token"),
            suffix=self._cloc.get("suffix"),
            folders_to_skip=self._cloc.get("folders_to_skip"),
            names_to_skip=self._cloc.get("names_to_skip"),
            exclude_tests=self._cloc.get("exclude_tests", False),
        )

    def get_code_coverage(self):
        """Get code coverage for repository."""
        return _get_code_coverage(repo_slug=self.repo_slug, branch=self.branch)

    def get_metadata(self):
        """Get Integration test metadata"""
        raise NotImplementedError("Need to implement at project level.")


@define
class Project:
    """Project (component) which hold different repos information."""

    name: str
    default_config: dict = field(repr=False)
    project_group: ProjectGroup = None
    _conf_path: Path = field(default=CONF_PATH, repr=False)
    _conf: Box = None

    @property
    def config(self):
        """Actual config, merged default config with project level."""
        if not self._conf:
            path = self._conf_path / f"{self.name}.yaml"
            assert path.exists(), f"Component config path not found {path.resolve()}"
            comp_conf = load_file(path=path)
            # Need to match with default (dyanaconf) conf.
            self._conf = merge_dicts(self.default_config, comp_conf)
        return self._conf

    @property
    def repositories(self):
        """Return list repository objects."""
        config = self.config
        repos = []
        for repo in config.repos:
            # Include github auth_token to repo level for cloc metrics
            if not hasattr(repo, "cloc"):
                repo["cloc"] = {}
            repo["cloc"]["auth_token"] = config.get("github", {}).get("token")
            # Include
            repos.append(Repository.from_config(rep_conf=repo))
        return repos

    def get_jira_issues(self):
        config = self.config.jira
        if config.project:
            return _get_issues(**config), config.project
        return {}, None
