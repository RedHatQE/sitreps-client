from logging import getLogger
from pathlib import Path

from cached_property import cached_property

from sitreps_client.cloc import get_cloc as _get_cloc
from sitreps_client.code_coverage import get_code_coverage as _get_code_coverage
from sitreps_client.issues import get_issues as _get_issues
from sitreps_client.sonarqube import get_sonar_metrics as _get_sonar_metrics
from sitreps_client.unit_tests import get_unit_tests as _get_unit_tests
from sitreps_client.utils.helpers import load_file
from sitreps_client.utils.helpers import merge_dicts
from sitreps_client.utils.path import CONF_PATH

SUPPORTED_HOSTS = ("github", "gitlab-cee", "gitlab")
SUPPORTED_CLOC_ARGS = {"suffix", "folders_to_skip", "names_to_skip", "exclude_tests", "auth_token"}
SUPPORTED_UNITTEST_ARGS = {"travis", "gh_action", "jenkins"}
SUPPORTED_SONARQUBE_ARGS = {"project_key", "host", "token"}
LOGGER = getLogger(__name__)


class ProjectGroup:
    """Project Group (bundle) which hold different Projects (components)."""

    def __init__(self, name: str, title: str, projects: list = None):
        self.name = name
        self.title = title
        self.projects = projects if projects else []

    def __repr__(self):
        return f"ProjectGroup({self.name})"


class Repository:
    """Project repository."""

    def __init__(
        self,
        title: str,
        url: str,
        branch: str = "master",
        type: str = "test",
        cloc: dict = None,
        sonarqube: dict = None,
        unit_tests: dict = None,
    ):
        self.title = title
        self.url = url
        self.branch = branch
        self.type = type
        self._cloc = cloc if cloc else {}
        self._sonarqube = sonarqube if sonarqube else {}
        self._unit_tests = unit_tests if unit_tests else {}

        if self._cloc and not set(self._cloc.keys()).issubset(SUPPORTED_CLOC_ARGS):
            raise ValueError(
                f"Supported cloc params are: {SUPPORTED_CLOC_ARGS} and provided: "
                f"{self._cloc.keys()}"
            )
        if self._sonarqube and not set(self._sonarqube.keys()).issubset(SUPPORTED_SONARQUBE_ARGS):
            raise ValueError(
                f"Supported sonarqube params are: {SUPPORTED_SONARQUBE_ARGS} and provided: "
                f"{self._sonarqube.keys()}"
            )

        if self._unit_tests and not set(self._unit_tests.keys()).issubset(SUPPORTED_UNITTEST_ARGS):
            raise ValueError(
                f"Supported unit tests params are: {SUPPORTED_UNITTEST_ARGS} and provided: "
                f"{self._unit_tests.keys()}"
            )

    @classmethod
    def from_config(cls, rep_conf):
        return cls(
            title=rep_conf.get("title"),
            url=rep_conf.get("url"),
            branch=rep_conf.get("branch", "master"),
            type=rep_conf.get("type", "test"),
            cloc=rep_conf.get("cloc"),
            sonarqube=rep_conf.get("sonarqube"),
            unit_tests=rep_conf.get("unit_tests"),
        )

    @property
    def repo_slug(self):
        """Return repo-slug of repository."""
        url = self.url.rstrip("/")
        components = url.split("/")
        return "/".join(components[-2:])

    @cached_property
    def name(self):
        """Return name of repository."""
        return self.repo_slug.split("/")[-1]

    @cached_property
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

    def get_unit_tests(self):
        """Get Unit tests count."""
        _args = {}
        if "travis" in self._unit_tests and self._unit_tests.travis.is_private is not None:
            LOGGER.debug(f"Travis is enabled for {self.title}")
            _args["travis"] = self._unit_tests.travis
            _args["travis"]["repo_slug"] = self.repo_slug
            _args["travis"]["branch"] = self.branch

        if "gh_action" in self._unit_tests and self._unit_tests.gh_action.workflow is not None:
            LOGGER.debug(f"GitHub Actions is enabled for {self.title}")
            _args["gh_action"] = self._unit_tests.gh_action
            _args["gh_action"]["repo_slug"] = self.repo_slug
            _args["gh_action"]["branch"] = self.branch

        if "jenkins" in self._unit_tests and self._unit_tests.jenkins.url is not None:
            LOGGER.debug(f"Jenkins is enabled for {self.title}")
            _args["jenkins"] = self._unit_tests.jenkins
        if _args:
            return _get_unit_tests(**_args)
        LOGGER.info(f"[UnitTests-{self.repo_slug}]: Not enabled.")

    def get_sonar_metrics(self):
        _args = self._sonarqube
        _args["branch"] = self.branch
        if "project_key" in _args:
            return _get_sonar_metrics(**_args)
        LOGGER.info(f"[SonarQube-{self.repo_slug}]: Not enabled.")

    def __repr__(self):
        return f"Repository(name={self.name}, type={self.type}, branch={self.branch})"


class Project:
    """Project (component) which hold different repos information."""

    def __init__(
        self,
        name: str,
        default_config: dict,
        project_group: ProjectGroup = None,
        conf_path: Path = CONF_PATH,
    ):
        self.name = name
        self.default_config = default_config
        self.project_group = project_group
        self._conf_path = conf_path

    @cached_property
    def config(self):
        """Actual config, merged default config with project level."""
        path = self._conf_path / f"{self.name}.yaml"
        assert path.exists(), f"Component config path not found {path.resolve()}"
        comp_conf = load_file(path=path)
        # Need to match with default (dyanaconf) conf.
        conf = merge_dicts(self.default_config, comp_conf)
        return conf

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

    def __repr__(self):
        return f"Project({self.name})"
