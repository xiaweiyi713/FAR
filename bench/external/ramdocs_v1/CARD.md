# RAMDocs v1 external evaluation slice

This directory is a deterministic import of `HanNight/RAMDocs` at Hugging Face
revision `9c041bfd158c603b615883d9a931b00cbc141494` (MIT). It contains 500
questions and a locally frozen 350/150 dev/test partition using seed 1729.

RAMDocs is independently published and upstream-labelled, but it is not treated
as independently double-annotated human gold in FAR. Valid answers originate in
AmbigDocs; misinformation documents are constructed by entity/answer replacement
and noise documents are retrieved. The held-out split is locally fingerprinted,
not externally custodied.

Rebuild and verify with:

```bash
uv run falsirag-build-ramdocs build --output-dir bench/external/ramdocs_v1
uv run falsirag-build-ramdocs verify --output-dir bench/external/ramdocs_v1
```
