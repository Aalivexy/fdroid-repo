import functools
import yaml
import requests
import jq
import shutil
import sys
import os
import base64
import logging
from pathlib import Path
from dacite import from_dict
from models import Package, RepoConfig, RepoData, FdroidIndexV2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

repo = from_dict(RepoData, yaml.safe_load(open("repo.yml", "r")))
script_dir = Path(__file__).parent.absolute()
env_file = script_dir / "env.yml"
icon_path = script_dir / "icon.png"
fdroid_dir = script_dir / "fdroid"
metadata_dir = fdroid_dir / "metadata"
repo_dir = fdroid_dir / "repo"
icon_file = fdroid_dir / "icon.png"
config_file = fdroid_dir / "config.yml"
banned_keys = [
    "RepoType",
    "Repo",
    "Binaries",
    "Builds",
    "ArchivePolicy",
    "AutoUpdateMode",
    "UpdateCheckMode",
    "VercodeOperation",
    "UpdateCheckIgnore",
    "UpdateCheckName",
    "UpdateCheckData",
    "CurrentVersion",
    "CurrentVersionCode",
    "NoSourceSince",
    "Provides",
]


def normalize_version(version: str | int | float) -> str:
    version_str = str(version).lower()
    return version_str[1:] if version_str.startswith("v") else version_str


def get_current_repo() -> FdroidIndexV2 | None:
    url = f"{repo.config.repo_url}/index-v2.json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return from_dict(FdroidIndexV2, resp.json())
    except Exception:
        logging.warning("Failed to fetch current repo data")
        return None


def get_package_info(pkg: Package) -> tuple[str, str]:
    try:
        response = get_data_from_url(pkg.info_url)
        if not response:
            logging.error(f"Failed to fetch data from {pkg.info_url}")
            sys.exit(1)

        data = response.json()

        version = (
            jq.compile(pkg.version_jq.replace("$PKG_NAME", pkg.pkg_name))
            .input_value(data)
            .first()
        )
        if not version:
            logging.error(f"Failed to extract version from {pkg.info_url}")
            sys.exit(1)

        download = (
            jq.compile(pkg.download_jq.replace("$PKG_NAME", pkg.pkg_name))
            .input_value(data)
            .first()
        )
        if not download:
            logging.error(f"Failed to extract download URL from {pkg.info_url}")
            sys.exit(1)

        return normalize_version(version), download

    except Exception as e:
        logging.error(f"Failed to fetch package info from {pkg.info_url}: {e}")
        sys.exit(1)


@functools.lru_cache(maxsize=None)
def get_data_from_url(
    url: str, max_retries: int = 3, retry_delay: float = 2.0
) -> requests.Response:
    if not url:
        return b""
    headers = {}
    if (
        url.startswith("https://api.github.com/")
        or url.startswith("https://raw.githubusercontent.com/")
        or url.startswith("https://github.com/")
    ):
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

    retry_count = 0
    last_exception = None

    while retry_count <= max_retries:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except Exception as e:
            last_exception = e
            retry_count += 1
            if retry_count <= max_retries:
                logging.warning(f"Request to {url} failed, attempt {retry_count}: {e}")
                import time

                time.sleep(retry_delay * retry_count)
            else:
                logging.error(
                    f"Request to {url} failed after {max_retries} attempts: {e}"
                )

    logging.error(f"Failed to fetch data from {url}: {last_exception}")
    sys.exit(1)


def check_for_updates() -> bool:
    if os.environ.get("REBUILD"):
        logging.info("REBUILD environment variable found, forcing update")
        return True

    current_repo = get_current_repo()
    if not current_repo:
        return True

    for pkg in repo.packages:
        logging.info(f"Checking for updates for {pkg.pkg_name}")

        version, download = get_package_info(pkg)
        if not version or not download:
            sys.exit(1)

        if current_repo.packages.get(pkg.pkg_name) is None:
            logging.info(f"{pkg.pkg_name} not found in current repo")
            return True

        is_up_to_date = False

        if version.isdigit():
            if int(version) == (
                current_repo.packages[pkg.pkg_name]
                .versions.popitem()[1]
                .manifest.versionCode
            ):
                is_up_to_date = True
        else:
            if normalize_version(
                current_repo.packages[pkg.pkg_name]
                .versions.popitem()[1]
                .manifest.versionName
            ).startswith(version):
                is_up_to_date = True

        if is_up_to_date:
            logging.info(f"{pkg.pkg_name} is up to date")
        else:
            logging.info(f"{pkg.pkg_name} has a new version: {version}")
            return True

    return False


def apply_env(config: RepoConfig) -> RepoConfig:
    for key, value in config.__dict__.items():
        if isinstance(value, str) and value.startswith("$"):
            env_var_name = value[1:]
            env_value = os.environ.get(env_var_name)
            if env_value is None:
                logging.error(f"Environment variable {env_var_name} not found")
                sys.exit(1)
            setattr(config, key, env_value)
    return config


def download_packages():
    try:
        if os.environ.get("DEL_EXISTING") and fdroid_dir.exists():
            shutil.rmtree(fdroid_dir)
            logging.info("Removed existing fdroid directory")
    except Exception as e:
        logging.warning(f"Failed to remove fdroid directory: {e}")

    repo_dir.mkdir(parents=True, exist_ok=True)
    logging.info("Created directory structure for F-Droid")

    if icon_path.exists():
        icon_file.write_bytes(icon_path.read_bytes())
    else:
        logging.warning("icon.png not found, skipping icon copy")

    config_file.write_text(yaml.safe_dump(repo.config.__dict__, sort_keys=False))
    config_file.chmod(0o600)
    logging.info("Created config.yml file")

    keycontent = os.environ.get("keycontent")
    if not keycontent:
        logging.error("keycontent environment variable not found")
        sys.exit(1)
    (fdroid_dir / repo.config.keystore).write_bytes(base64.b64decode(keycontent))
    logging.info("Keystore file created")

    metadata_dir.mkdir(parents=True, exist_ok=True)
    for pkg in repo.packages:
        new_icon_file = metadata_dir / f"{pkg.pkg_name}/en-US/images/icon.png"
        new_icon_file.parent.mkdir(parents=True, exist_ok=True)
        new_icon_file.write_bytes(get_data_from_url(pkg.icon_url).content)

        metadata_file = metadata_dir / f"{pkg.pkg_name}.yml"
        metadata = dict()
        if pkg.metadata_url:
            metadata = {
                **metadata,
                **yaml.safe_load(
                    get_data_from_url(
                        pkg.metadata_url.replace("$PKG_NAME", pkg.pkg_name)
                    ).content
                ),
            }
        if pkg.info_url.endswith("index-v2.json"):
            fdroid = from_dict(FdroidIndexV2, get_data_from_url(pkg.info_url).json())
            if fdroid.packages.get(pkg.pkg_name):
                data = fdroid.packages[pkg.pkg_name].metadata
                if not metadata.get("Summary"):
                    metadata["Summary"] = data.summary.get("en-US", data.summary)
                if not metadata.get("Description"):
                    metadata["Description"] = data.description.get(
                        "en-US", data.description
                    )
        if pkg.metadata:
            metadata = {**metadata, **pkg.metadata}
        metadata = {
            k: v
            for k, v in metadata.items()
            if k not in banned_keys and v is not None and v != ""
        }
        metadata["Categories"].append(repo.config.repo_name)
        if metadata.get("Name") is None and metadata.get("AutoName") is not None:
            metadata["Name"] = metadata["AutoName"]

        metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False))
        logging.info(f"Processed metadata for {pkg.pkg_name}")

        version, download = get_package_info(pkg)
        apk_file = repo_dir / f"{pkg.pkg_name}_v{version}.apk"
        if not apk_file.exists():
            apk_file.write_bytes(get_data_from_url(download).content)
            logging.info(f"Downloaded APK for {pkg.pkg_name}")


def create_fdroid_repo():
    from fdroidserver import __main__

    logging.info("Running fdroid update command")
    sys.argv = [
        "fdroid",
        "update",
        "--pretty",
        "--delete-unknown",
        "--use-date-from-apk",
        "--rename-apks",
    ]
    os.chdir(fdroid_dir)
    __main__.main()

    logging.info("F-Droid update process completed successfully")


def update_env():
    if env_file.exists():
        try:
            with open(env_file, "r") as f:
                env_vars = yaml.safe_load(f)
                if isinstance(env_vars, dict):
                    for key, value in env_vars.items():
                        if key not in os.environ:
                            os.environ[key] = str(value)
                    logging.info("Environment variables loaded from env.yml")
                else:
                    logging.warning(
                        "Invalid env.yml format, should be key-value dictionary"
                    )
        except Exception as e:
            logging.warning(f"Failed to load env.yml: {e}")


def main():
    update_env()
    repo.config = apply_env(repo.config)

    if not check_for_updates():
        logging.info("All packages are up to date")
        sys.exit(0)
    else:
        logging.info("Updates available, proceeding with download")

    download_packages()
    create_fdroid_repo()


if __name__ == "__main__":
    main()
