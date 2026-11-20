# Change Log

### v0.1.0+molonc.1

molonc baseline: upstream v0.1.0 plus the edits made by hand inside the
production images. Output is identical to those images. See MOLONC.md.

1. Metadata fields `pick_met` and `condition` renamed to `cell_call` and `experimental_condition`
2. `igvtools count` disabled when merging cell BAMs
3. Empty-regions assertion in coverage metrics disabled
4. Breakpoint consensus matching rewritten as a hash join
5. Consensus VCF and counts headers written once instead of per chromosome; empty inputs skipped in VCF merges
6. Release workflow that builds the images on ghcr.io from upstream's v0.1.0 images and verifies them

### v0.0.12

1. no change
