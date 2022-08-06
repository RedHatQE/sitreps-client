import time
from logging import getLogger
from typing import Any
from typing import Tuple

LOGGER = getLogger(__name__)


def wait_for(
    func, delay: float = 2.0, num_sec: float = 10.0, ignore_falsy: bool = False
) -> Tuple[Any, Any, int]:
    """Wait for success of `func` for `num_sec`."""
    end_time = time.time() + num_sec

    tries = 0

    while time.time() < end_time:
        response = None
        err = None
        tries += 1

        try:
            response = func()
        # pylint: disable=broad-except
        except Exception as exp:
            err = exp
            LOGGER.warning(f"{tries} tries fail, Handling exception: {err}")
            continue

        if response or ignore_falsy:
            return response, err, tries

        time.sleep(delay)

    return response, err, tries
