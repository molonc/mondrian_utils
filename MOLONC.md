# molonc fork of mondrian_utils

This fork holds the mondrian_utils code that molonc's production Mondrian
images run. [molonc/mondrian_nf](https://github.com/molonc/mondrian_nf) runs
those images from `ghcr.io/molonc/mondrian_utils/<image>`. Upstream is
[mondrian-scwgs/mondrian_utils](https://github.com/mondrian-scwgs/mondrian_utils),
configured as the `upstream` remote.

## Baseline

`main` starts at upstream `v0.1.0`, the version every production image
installed. Before this fork existed, the images ran from `mondrian.azurecr.io`,
and edits were made by hand inside running containers and committed to the
images. The baseline release, `v0.1.0+molonc.1`, reproduces those edits:

| Image | Date | Change |
|---|---|---|
| alignment, hmmcopy | 2024-10 | Metadata fields `pick_met` and `condition` renamed to `cell_call` and `experimental_condition` |
| alignment, hmmcopy | 2024-10 | `igvtools count` disabled in `merge_bams`; merged BAMs get no `.tdf` |
| alignment | 2025-02 | Empty-regions assertion in coverage metrics disabled |
| breakpoint_calling | 2026-06 | Breakpoint consensus matching rewritten as a hash join with deduplicated positions |
| variant_calling | 2026-06 | Consensus VCF and counts headers written once instead of per chromosome; empty inputs skipped in VCF merges |

Each image previously carried only its own edits. The code paths that each
image runs do not reach the edits made for the other images.

## Releases

Output must not change between releases unless a release states otherwise.

- Git tags take the form `v<upstream version>+molonc.<N>`, a PEP 440 local
  version: upstream `0.1.0` plus molonc release N. Upstream tags keep their
  own names.
- Image tags are the git tag with `+` replaced by `-`, because Docker tags
  cannot contain `+`. Every image in `docker/images.tsv` is rebuilt for every
  release and shares its tag, for example `alignment:v0.1.0-molonc.1`.
- Each production image on `mondrian.azurecr.io` is upstream's public
  `quay.io/mondrianscwgs/<image>:v0.1.0`, layer for layer, plus edits made by
  hand. Release images start from those upstream images, pinned by digest in
  `docker/images.tsv`, and add one layer: this repository's mondrian_utils and,
  for breakpoint_calling, the procps packages installed by hand in 2024 at the
  same versions. Every other tool stays byte-identical to production. The
  original images stay in `mondrian.azurecr.io` for runs that recorded them.
- The release workflow creates each `ghcr.io/molonc/mondrian_utils/<image>`
  package on its first push, which links the package to this repository. The
  packages are private: the HPC sites that run mondrian_nf pull them with a
  credential that can read packages.

A PR that adds a `### vX.Y.Z+molonc.N` heading to the top of `CHANGELOG.md`
is a release. When it merges, `.github/workflows/release.yml`:

1. tags the merge commit;
2. builds and pushes every image, refusing an image tag that already exists;
3. runs `docker/verify.py`, which checks that each image is its base image
   plus one layer holding exactly the tagged mondrianutils files;
4. publishes the GitHub Release with the changelog section.

A release image never changes after it is pushed. A release that fails a check
is replaced by the next `+molonc.N`. mondrian_nf then names the new tag in
`params.container_version`, and the iris analysis test confirms identical
output before production uses it.
