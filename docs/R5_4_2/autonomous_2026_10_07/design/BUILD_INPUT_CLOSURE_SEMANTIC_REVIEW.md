# Build-input closure — current executable gap review

Authority: complete Data 122–125 in the retained R5.3 source and the qualified
R5.4.1 predecessor; OD-027 separates application installation inputs from
campaign history. This review does not qualify a BuildManifest or installation.

The source and runtime collectors in `build/build_single_file.py` supply the
existing standalone recipe. A declared runtime distribution member previously
disappeared from the payload when its installed path was absent or a directory.
The corrected collector rejects that condition even when other files from the
same distribution are available. Its explicit script/cache exclusions remain
unchanged. Runtime bytes are retained exactly, including original line endings.

Three targeted regressions cover absent inputs, directory substitution and
exact-byte retention alongside excluded transport paths. The affected existing
build tests also exercise repeat-build byte identity, embedded manifests,
payload tampering and a clean isolated interpreter without host jsonschema.
The runtime-run record binds the builder, lock, source/test files and each actual
retained runtime dependency before and after execution. An ordinary repository
temporary directory replaces the host TEMP ACL failure for this diagnostic
execution; production algorithms and test expectations are unchanged.

The successor BuildManifest grammar has explicit CANONICAL/RAW/PROFILE input
branches. Thirty-one additional controls require each branch's reference,
reject mixed branches and duplicate entries in both declared-input arrays, and
reject a final output digest in the frozen input manifest. These are grammar
controls, not proof that the actual input denominator is complete.

Remaining requirements are substantive: independently selected qualified
application SourceGeneration; exact declared recipe, builder bytes/version,
schema/configuration/resource inputs and runtime/settings profiles; full
transitive byte closure frozen before building; no undeclared cwd, ignored-file,
clock or network input; independent output verification; external provenance
receipt with exact output/environment/verification refs; and exclusion of
future activation/qualification receipts from their own build preimage.

The current embedded path/size/hash dictionary is a payload integrity manifest.
It does not itself satisfy canonical BuildManifest/2, source authorization,
independent build provenance or successor installation qualification. Nine
passing local build regressions do not advance Q1, Q2 or N5–N11. The build node
and its dependent semantic obligations remain pending.
