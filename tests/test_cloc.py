from pathlib import Path

import pytest

from sitreps_client.cloc import get_cloc
from sitreps_client.cloc import PygountCloc


@pytest.mark.parametrize("_type", ["direct-path", "repo-slug"])
def test_cloc(_type):
    if _type == "direct-path":
        path = Path(".").parent.parent
        repo_slug = None
    else:
        path = None
        repo_slug = "digitronik/sitreps-server"
    cloc = get_cloc(path=path, repo_slug=repo_slug)
    assert cloc
    assert "Python" in cloc


TEST_DATA = {
    "suffix": {"suffix": "py"},
    "folders_to_skip": {"folders_to_skip": "utils"},
    "names_to_skip": {"names_to_skip": "cloc.py"},
    "exclude_tests": {},
}


@pytest.mark.parametrize("option", TEST_DATA.keys())
def test_cloc_option(option):
    args = TEST_DATA[option]

    pygountcloc = PygountCloc(path=Path(".").parent.parent, **args)

    if option != "exclude_tests":
        assert any(
            f"{option.replace('_', '-')}={args[option]}" in _arg for _arg in pygountcloc.arguments
        )
    else:
        assert pygountcloc.get_cloc(exclude_tests=False) > pygountcloc.get_cloc(exclude_tests=True)
