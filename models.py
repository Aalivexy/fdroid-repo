from dataclasses import dataclass


@dataclass
class RepoConfig:
    repo_name: str
    repo_url: str
    repo_description: str

    repo_keyalias: str
    keystore: str
    keystorepass: str
    keypass: str
    keydname: str


@dataclass
class PackageMetadataOverride:
    Name: str
    AuthorName: str
    License: str
    SourceCode: str
    Categories: list[str]


@dataclass
class PackageMetadata:
    icon_url: str
    url: str | None = None
    override: PackageMetadataOverride | None = None


@dataclass
class Package:
    pkg_name: str
    metadata: PackageMetadata
    info_url: str
    version_jq: str
    download_jq: str


@dataclass
class RepoData:
    config: RepoConfig
    packages: list[Package]


@dataclass
class FdroidPackageManifest:
    versionName: str


@dataclass
class FdroidPackageVersion:
    manifest: FdroidPackageManifest


@dataclass
class FdroidPackage:
    versions: dict[str, FdroidPackageVersion]


@dataclass
class FdroidIndexV2:
    packages: dict[str, FdroidPackage]
