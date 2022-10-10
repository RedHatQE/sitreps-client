"""Count cloc for project and tests repositories."""
import io
import logging
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict
from typing import Optional

from pygount.command import pygount_command

from sitreps_client.utils.repository import UnzipRepo


LOGGER = logging.getLogger(__name__)


class PygountCloc:
    """Use pygount to count CLOC.

    Args:
        path (Path): Project path.
        suffix (Union[str, None], optional): To limit the analysis on certain file types,
                                             eg. 'py,pyx,go,js,ts,rb,rs,md'.
        folders_to_skip (Union[str, None], optional): Folder you like to skip.
        names_to_skip (Union[str, None], optional): File name you like to skip.
    """

    DEFAULT_SUFFIX = "py,pyx,go,js,ts,rb,rs,md"

    def __init__(
        self,
        path: Path,
        suffix: Optional[str] = None,
        folders_to_skip: Optional[str] = None,
        names_to_skip: Optional[str] = None,
    ):
        self.path = path.expanduser().resolve()
        self.suffix = suffix
        self.folders_to_skip = folders_to_skip
        self.names_to_skip = names_to_skip

    @property
    def arguments(self):
        args = [str(self.path)]

        if self.suffix:
            LOGGER.info(f"Limiting pyground analysis with suffix: {self.suffix}")
            args.append(f"--suffix={self.suffix}")

        if self.folders_to_skip:
            args.append(f"--folders-to-skip={self.folders_to_skip}")

        if self.names_to_skip:
            args.append(f"--names-to-skip={self.names_to_skip}")

        LOGGER.info(f"Pygount args: {args}")
        return args

    def get_raw_cloc(self) -> str:
        """Get raw output from pygount."""
        with io.StringIO() as buf, redirect_stdout(buf):
            pygount_command(self.arguments)
            res = buf.getvalue()
        return res

    def get_cloc_per_lang(self, exclude_tests: bool = False) -> Dict[str, int]:
        """Get stats per language, with tests code included or excluded.
        Args:
            exclude_tests (bool): Exclude test/test file from analysis.
        """
        raw_cloc = self.get_raw_cloc()
        files_rec = raw_cloc.replace("\t", " ").split("\n")
        lang_cloc: Dict[str, int] = {}

        for rec in files_rec:
            rec = rec.strip()
            if not rec or rec.startswith("0 "):
                continue
            num_str, lang, *__, path = rec.split(" ")

            if exclude_tests and any(n in path for n in ("/test", "_test", "test_")):
                LOGGER.warning(f"Excluding '{path}' as detected as test file.")
                continue

            num = int(num_str)
            if lang not in lang_cloc:
                lang_cloc[lang] = 0
            lang_cloc[lang] += num

        LOGGER.info(f"CLOC: {lang_cloc}")
        return lang_cloc

    def get_cloc(self, exclude_tests: bool = False) -> int:
        """Count total cloc as a sum of cloc of all considered languages."""
        cloc_stats = self.get_cloc_per_lang(exclude_tests=exclude_tests)
        total = 0
        for count in cloc_stats.values():
            total += count
        return total

    def __repr__(self):
        return f"<PygountCloc(path={str(self.path)})>"


def get_cloc(
    path: Optional[Path] = None,
    repo_slug: Optional[str] = None,
    provider: str = "github",
    auth_token: str = "",
    branch: str = "master",
    suffix: Optional[str] = None,
    folders_to_skip: Optional[str] = None,
    names_to_skip: Optional[str] = None,
    exclude_tests: bool = False,
) -> Optional[dict]:
    """Collect CLOC

    Args:
        path (Path): Project path.
        repo_slug (str): Repository slug <org:owner>.
        provider (str): Repository codebase (github/gitlab/gitlab-cce). Default "github".
        auth_token (str): Token for downloading protected repositories.
        branch (str): Repository branch
        suffix (str): To limit the analysis on certain file types,
                      Defaults to 'py,pyx,go,js,ts,rb,rs,md'.
        folders_to_skip (str): Folder you like to skip.
        names_to_skip (str): File name you like to skip.
        exclude_tests (bool): Do you like to skip tests.
    """
    assert path or repo_slug, "You need to specify path or repo_slug"
    cloc = {}
    if path:
        LOGGER.info(f"Pygount using direct path: {path}.")
        _pygountcloc = PygountCloc(
            path=path, suffix=suffix, folders_to_skip=folders_to_skip, names_to_skip=names_to_skip
        )
        cloc = _pygountcloc.get_cloc_per_lang(exclude_tests=exclude_tests)

    if not path and repo_slug:
        LOGGER.info(f"Pygount using repo-slug for path: {repo_slug}.")
        with UnzipRepo(
            repo_slug=repo_slug,
            provider=provider,
            auth_token=auth_token,
            branch=branch,
        ) as dest:
            _pygountcloc = PygountCloc(
                path=dest,
                suffix=suffix,
                folders_to_skip=folders_to_skip,
                names_to_skip=names_to_skip,
            )
            cloc = _pygountcloc.get_cloc_per_lang(exclude_tests=exclude_tests)
    return cloc


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    from pathlib import Path

    cloc_path = get_cloc(path=Path(".").parent.parent)
    print(cloc_path)
    cloc_repo = get_cloc(repo_slug="insights-qe/iqe-patchman-plugin", provider="gitlab-cce")
    print(cloc_repo)
