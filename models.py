from dataclasses import dataclass, field


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
class Package:
    pkg_name: str
    info_url: str
    icon_url: str | None = None
    metadata_url: str | None = None
    metadata: dict | None = None
    version_jq: str | None = None
    download_jq: str | None = None


@dataclass
class RepoData:
    config: RepoConfig
    packages: list[Package]


@dataclass
class FdroidPackageManifest:
    versionName: str
    versionCode: int
    nativecode: list[str] | None = None


@dataclass
class FdroidPackageFile:
    name: str
    sha256: str
    size: int


@dataclass
class FdroidPackageVersion:
    file: FdroidPackageFile
    manifest: FdroidPackageManifest
    releaseChannels: list[str] | None = None


@dataclass
class IconInfo:
    name: str
    sha256: str
    size: int


@dataclass
class FdroidPackageMetadata:
    name: dict[str, str] | None = None
    summary: dict[str, str] | None = None
    description: dict[str, str] | None = None
    icon: dict[str, IconInfo] | None = None
    authorName: str | None = None
    authorEmail: str | None = None
    authorWebSite: str | None = None
    webSite: str | None = None
    sourceCode: str | None = None
    changelog: str | None = None
    issueTracker: str | None = None
    license: str | None = None
    categories: list[str] | None = None
    donate: list[str] | None = None
    translation: str | None = None


@dataclass
class FdroidPackage:
    metadata: FdroidPackageMetadata
    versions: dict[str, FdroidPackageVersion] = field(default_factory=dict)


@dataclass
class FdroidIndexV2:
    packages: dict[str, FdroidPackage] = field(default_factory=dict)
