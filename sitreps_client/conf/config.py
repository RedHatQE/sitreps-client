import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

from sitreps_client.utils.helpers import load_file

LOGGER = logging.getLogger(__name__)


def get_config_path():
    """Default config path as per platfrom."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        config_home = Path(xdg_config_home)
    else:
        config_home = Path.home() / ".config"

    return config_home / "sitreps"


PROJECT_PATH = Path(__name__).parent.expanduser().resolve()
DEFAULT_CONFIG_DATA = PROJECT_PATH / "sitreps_client/conf/default_settings.yaml"
DEFAULT_CONFIG_PATH = get_config_path() / "settings.yaml"
DEFAULT_ENV_PATH = get_config_path() / "env"

# Load secrets
ENV_FILE = str(DEFAULT_ENV_PATH.absolute()) if DEFAULT_ENV_PATH.exists() else ""
load_dotenv(ENV_FILE)

# Jira secrets
JIRA_URL = os.getenv("JIRA_URL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD")

# Github secretes
GH_TOKEN = os.getenv("GH_TOKEN")

# Jenkins secrets
JENKINS_USERNAME = os.getenv("JENKINS_USERNAME")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")


def write_default_config(outpath=None):
    outpath = Path(outpath) if outpath else DEFAULT_CONFIG_PATH
    outpath.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    inpath = Path(DEFAULT_CONFIG_DATA)
    shutil.copy(inpath, outpath)
    outpath.chmod(0o600)
    LOGGER.info("saved config to: %s", outpath.absolute())


# def edit_default_config(confpath=None):
#     confpath = Path(confpath) if confpath else DEFAULT_CONFIG_PATH
#     if os.getenv("EDITOR") is None:
#         log.info("No $EDITOR set, exiting.")
#         return

#     subprocess.call([os.getenv("EDITOR"), confpath])


def load_config(config_path=None):
    if config_path:
        LOGGER.debug("User provided explicit config path: %s", config_path)
        config_path = Path(config_path)
        if not config_path.exists():
            raise ValueError(f"provided config file path '{str(config_path)}' does not exist")
    else:
        LOGGER.debug("Using default config path: %s", DEFAULT_CONFIG_PATH)
        config_path = DEFAULT_CONFIG_PATH
        if not config_path.exists():
            LOGGER.info("default config not found, creating")
            write_default_config()

    LOGGER.info("reading config from: %s", str(config_path.absolute()))
    default_config = load_file(config_path)
    return default_config


if __name__ == "__main__":
    from pprint import pprint

    config = load_config()
    default_config = config.get("default")
    pprint(config)
