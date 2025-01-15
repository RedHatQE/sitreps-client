import pytest

from sitreps_client.code_coverage import CodecovCoverage


@pytest.mark.parametrize(
    "slug", ["digitronik/varmeth", "digitronik/wrong"], ids=["correct", "wrong"]
)
def test_code_coverage(slug):
    codecov = CodecovCoverage(repo_slug=slug)

    if "wrong" in slug:
        assert not codecov.get_coverage()
    else:
        assert codecov.get_coverage()
