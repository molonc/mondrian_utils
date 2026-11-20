# Rebuild a production Mondrian image with one release of this repository.
#
# BASE_IMAGE is upstream's image, pinned by digest (see images.tsv), so every
# tool other than mondrian_utils stays byte-identical to production. The base
# images installed mondrian_utils into the base conda environment with pip;
# reinstalling with the same interpreter replaces that copy.
#
# APT_PACKAGES restores packages that were installed by hand in production,
# pinned to the installed versions. The bases run Debian releases that only
# archive.debian.org still serves. One RUN keeps the release to a single layer
# above the base, which docker/verify.py checks.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Some bases set `conda run` as their build shell. The commands below name
# their interpreter, so plain bash suffices and reports failures directly.
SHELL ["/bin/bash", "-c"]

ARG APT_PACKAGES=""
ARG MONDRIAN_UTILS_COMMIT
ARG MONDRIAN_UTILS_VERSION

RUN set -eu; \
    if [ -n "${APT_PACKAGES}" ]; then \
        . /etc/os-release; \
        printf 'deb http://archive.debian.org/debian %s main\ndeb http://archive.debian.org/debian-security %s/updates main\n' \
            "${VERSION_CODENAME}" "${VERSION_CODENAME}" > /etc/apt/sources.list; \
        apt-get -o Acquire::Check-Valid-Until=false update; \
        apt-get install -y --no-install-recommends ${APT_PACKAGES}; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    /opt/conda/bin/python -m pip install --no-deps --force-reinstall --no-cache-dir \
        "git+https://github.com/molonc/mondrian_utils.git@${MONDRIAN_UTILS_COMMIT}"

LABEL org.opencontainers.image.source="https://github.com/molonc/mondrian_utils" \
      org.opencontainers.image.revision="${MONDRIAN_UTILS_COMMIT}" \
      org.opencontainers.image.version="${MONDRIAN_UTILS_VERSION}" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"
