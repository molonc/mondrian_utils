#!/usr/bin/env python3
"""Verify that a release's images contain exactly that release of mondrian_utils.

Usage: python3 docker/verify.py v0.1.0+molonc.1

Each image in images.tsv is published as
``ghcr.io/molonc/mondrian_utils/<name>`` with the release tag, "+" replaced by
"-". The release image must:

* consist of its base image's layers followed by one new layer;
* hold in that layer exactly the ``mondrianutils`` files of the release tag,
  replacing the base image's copy in the same ``site-packages`` directory;
* report the release version in its package metadata and the release commit
  in its labels.

The base layers are byte-identical by digest, so the new layer is the only
difference from the base. Bases are read anonymously. ``GHCR_TOKEN`` (with
``GHCR_USER`` or ``GITHUB_ACTOR``) is sent only to ghcr.io, to read release
images that are not public. The checks only read. The script exits nonzero
when any check fails.
"""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_HOST = "ghcr.io"
RELEASE_NAMESPACE = "molonc/mondrian_utils"
MANIFEST_TYPES = ", ".join(
    [
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    ]
)
OPAQUE = ".wh..wh..opq"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface blob redirects so the registry token is not sent to storage."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def git(*args, binary=False):
    """Run git in the repository root and return its output."""
    result = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True)
    return result.stdout if binary else result.stdout.decode().strip()


def parse_reference(reference):
    """Split ``host/repository:tag@digest`` into its parts."""
    name, _, digest = reference.partition("@")
    host, path = name.split("/", 1)
    repository, _, tag = path.rpartition(":")
    return host, repository, tag, digest


class Registry:
    """Read manifests and blobs from one repository with a pull token."""

    def __init__(self, host, repository):
        self.host, self.repository = host, repository
        self.token = self._token()

    def _token(self):
        """Answer the registry's bearer challenge; only ghcr.io gets credentials."""
        try:
            urllib.request.urlopen(f"https://{self.host}/v2/")
            return None
        except urllib.error.HTTPError as error:
            challenge = error.headers.get("WWW-Authenticate", "")
        params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        query = urllib.parse.urlencode(
            {"service": params.get("service", self.host), "scope": f"repository:{self.repository}:pull"}
        )
        request = urllib.request.Request(f"{params['realm']}?{query}")
        if self.host == RELEASE_HOST and os.environ.get("GHCR_TOKEN"):
            user = os.environ.get("GHCR_USER") or os.environ.get("GITHUB_ACTOR") or "token"
            secret = base64.b64encode(f"{user}:{os.environ['GHCR_TOKEN']}".encode()).decode()
            request.add_header("Authorization", f"Basic {secret}")
        with urllib.request.urlopen(request) as response:
            body = json.load(response)
        return body.get("token") or body.get("access_token")

    def fetch(self, path, accept=None):
        """GET a path under /v2/<repository>/, following a redirect without the token."""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        if accept:
            headers["Accept"] = accept
        url = f"https://{self.host}/v2/{self.repository}/{path}"
        try:
            with _OPENER.open(urllib.request.Request(url, headers=headers)) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                with urllib.request.urlopen(error.headers["Location"]) as response:
                    return response.read()
            raise

    def manifest(self, reference):
        """Return an image manifest by tag or digest."""
        return json.loads(self.fetch(f"manifests/{reference}", MANIFEST_TYPES))


def release_tree(release):
    """Return {path under mondrianutils/: sha256} for the release tag."""
    tree = {}
    for path in git("ls-tree", "-r", "--name-only", release, "--", "mondrianutils").splitlines():
        blob = git("cat-file", "blob", f"{release}:{path}", binary=True)
        tree[path[len("mondrianutils/"):]] = hashlib.sha256(blob).hexdigest()
    return tree


def layer_contents(blob):
    """Read the mondrianutils files, whiteouts and package version of a layer."""
    files, whiteouts, directories, versions = {}, [], set(), []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as archive:
        for member in archive:
            name = member.name[2:] if member.name.startswith("./") else member.name
            if "/site-packages/" not in name:
                continue
            directory, rest = name.split("/site-packages/", 1)
            base = os.path.basename(rest)
            if base.startswith(".wh.") and base != OPAQUE:
                whiteouts.append((directory, os.path.join(os.path.dirname(rest), base[4:])))
            elif rest.startswith("mondrianutils/") and member.isfile():
                path = rest[len("mondrianutils/"):]
                if base == OPAQUE or "__pycache__" in path or path.endswith(".pyc"):
                    continue
                files[path] = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                directories.add(directory)
            elif rest.startswith("mondrianutils-") and rest.endswith(".dist-info/METADATA"):
                for line in archive.extractfile(member).read().decode().splitlines():
                    if line.startswith("Version: "):
                        versions.append(line[len("Version: "):])
    return files, whiteouts, directories, versions


def verify_image(name, base, release, commit, expected):
    """Return the release image and the problems found in it."""
    image_tag = release.replace("+", "-")
    image = f"{RELEASE_HOST}/{RELEASE_NAMESPACE}/{name}:{image_tag}"
    registry = Registry(RELEASE_HOST, f"{RELEASE_NAMESPACE}/{name}")
    try:
        manifest = registry.manifest(image_tag)
    except urllib.error.HTTPError as error:
        return image, [f"not found ({error.code})"]

    problems = []
    base_host, base_repository, _, base_digest = parse_reference(base)
    base_manifest = Registry(base_host, base_repository).manifest(base_digest)
    base_layers = [layer["digest"] for layer in base_manifest["layers"]]
    layers = [layer["digest"] for layer in manifest["layers"]]
    if layers[:-1] != base_layers:
        problems.append("layers below the top layer differ from the base image")
    if len(layers) != len(base_layers) + 1:
        problems.append(f"expected {len(base_layers) + 1} layers, found {len(layers)}")

    files, whiteouts, directories, versions = layer_contents(registry.fetch(f"blobs/{layers[-1]}"))
    files.pop("_version.py", None)
    wanted = {path: digest for path, digest in expected.items() if path != "_version.py"}
    differ = sorted(p for p in set(files) | set(wanted) if files.get(p) != wanted.get(p))
    if differ:
        problems.append(f"mondrianutils files differ from {release}: {differ}")
    if len(directories) != 1:
        problems.append(f"mondrianutils installed in {sorted(directories) or 'no'} site-packages")
    replaced = [p for d, p in whiteouts if d in directories and p.startswith("mondrianutils-")]
    if not replaced:
        problems.append("the base image's mondrianutils install was not replaced in place")
    if versions != [release[1:]]:
        problems.append(f"package version {versions}, expected {release[1:]}")

    config = json.loads(registry.fetch(f"blobs/{manifest['config']['digest']}"))
    labels = config.get("config", {}).get("Labels") or {}
    if labels.get("org.opencontainers.image.revision") != commit:
        problems.append(f"revision label {labels.get('org.opencontainers.image.revision')}")
    if labels.get("org.opencontainers.image.version") != release:
        problems.append(f"version label {labels.get('org.opencontainers.image.version')}")
    return image, problems


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    release = sys.argv[1]
    commit = git("rev-parse", f"{release}^{{commit}}")
    expected = release_tree(release)
    failed = False
    with open(os.path.join(ROOT, "docker", "images.tsv")) as images:
        for line in images:
            if not line.strip() or line.startswith("#"):
                continue
            name, base = line.rstrip("\n").split("\t")[:2]
            if "@sha256:" not in base:
                print(f"FAIL {name}: images.tsv base {base!r} is not pinned by digest")
                failed = True
                continue
            image, problems = verify_image(name, base, release, commit, expected)
            failed |= bool(problems)
            print(f"FAIL {image}: " + "; ".join(problems) if problems else f"PASS {image}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
