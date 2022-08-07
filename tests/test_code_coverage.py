import pytest
from sitreps_client.code_coverage import CodecovCoverage
from sitreps_client.exceptions import CodeCoverageError



@pytest.mark.parametrize("slug", ["digitronik/varmeth", "digitronik/wrong"], ids=["correct", "wrong"])
def test_code_coverage_is_available(slug):
    codecov = CodecovCoverage(repo_slug=slug, branch="master")

    if "wrong" in slug:
        assert not codecov.is_available
    else:
        assert codecov.is_available


@pytest.mark.parametrize("branch", ["master", "foo"], ids=["correct", "wrong"])
def test_code_coverage_branch(branch):
    codecov = CodecovCoverage(repo_slug="digitronik/varmeth", branch=branch)

    if branch == "master":
        assert codecov.get_coverage()
    else:
        with pytest.raises(CodeCoverageError) as error:
            codecov.get_coverage()
        assert "Branch not found" in str(error.value)
