# Source identity and complete-source eligibility

Full source: qualified Data section 8 and dependencies 8.1–8.4. OD-028 closes
the inherited arbitrary completeness_state string. No source instance is
qualified or installed by this review.

Historical SourceManifest/1 retains its exact predecessor schema. OD-030's
SourceManifest/2 corrects only its canonical source path shape. Canonical relative
POSIX paths, sorted unique entries, actual original retained bytes/modes and
type-specific symlink/submodule/LFS facts are independently verified. Missing
required content cannot be omitted or count as COMPLETE_SOURCE. Syntax alone
does not establish complete materialization or RawDigest equality.

SourceIdentity/2 binds the exact manifest, SOURCE_IDENTITY_V3 and independently
authorized SOURCE_AUTHORITY_V1. AUTHORIZED_GIT requires reconciled actual exact
commit/tree IDs under the pinned algorithm. Snapshot source cannot impersonate
Git identity. Same-commit matching hashes/descriptor strings cannot install the
authority used to authenticate their own identity/generation.

COMPLETE_SOURCE and BOUNDED_SOURCE are finite representational states.
Complete-source admission additionally requires independently verified complete
manifest/materialization and all source/profile guards. A caller declaration is
no proof. BOUNDED_SOURCE retains limitations and grants no completeness. Unknown
or unverified context rejects, not a invented success/unknown accepted token.
SOURCE_IDENTITY_V3's REJECT rule for unresolved required LFS/submodules remains.

SourceGeneration/2 must resolve the same exact identity/manifest/profile and
authorized source context. Logical generation IDs are aliases, not authority:
enforce one-to-one exact identity mapping and explicit import-alias relation.
Parent generations remain exact prior accepted. Archive digest/name identifies
representation only. Material source changes require a new generation and
independent evidence requalification; archive renaming cannot change identity.

Bootstrap requires actual source manifest/identity/generation bodies in typed
dependency order before legacy reconciliation/admission, under independent
installed authority. Application build source (OD-027) remains separate from
the audited target, even when bytes coincide. No source guard is established
merely because a command precedes or follows source objects.

Remaining: trusted source resolution, exact raw-byte/manifest reconciliation,
full instance DAG and schema bindings, alias-conflict rejection, LFS/submodule
omission and forged completeness, stale parents, archive/source substitution,
bootstrap source mismatch, and durable rejection atomicity. This review and
finite grammar vectors do not complete the semantic queue node.

OD-029 additionally closes the previously omitted path/entry/policy parameters
explicitly required by Data 8.1. SOURCE_PATH_PROFILE_V1 selects the inherited
successor manifest path shape plus component/alias guards and exact byte order;
unsupported names reject completeness instead of omission. Entry profile pins
the exact qualified source_manifest/2 schema raw bytes and selects its entry
grammar without copying a second schema authority. Explicit source-type policies
and one-to-one authority parameters determine mode/Git algorithm before identity
validation. Snapshot NONE cannot satisfy a Git algorithm; Git SHA1/SHA256 is
independently authorized, never inferred from user-supplied ID length. Grammar
tests verify finite representation only; complete authority coverage, source
readback, algorithm reconciliation and durable execution are still pending.

OD-030 actual input probe retains a 499-entry manifest of exact committed HEAD,
using the current authoritative Git resolver/materializer and canonical serializer.
The predecessor rejects three dot-prefixed paths; /2 accepts the entire manifest.
The dirty application build is a distinct source context and is not substituted
with this committed dataset. SOURCE_INSTANCE_READBACK stores exact source commit,
tree, object algorithm, implementation/schema/body raw hashes and /2 ObjectDigest.

OD-031's source archive selects the exact SourceGeneration content-or-prior
manifest, not unavailable prior acceptance during first bootstrap. Its transport
is separately pinned SOURCE_ZIP_TRANSPORT_V1, preserving NF02 package transport.
Actual source_head_representation.zip retains all 499 material members with exact
original bytes and manifest modes. Git archive permission metadata is explicitly
replaced with independently read manifest modes; source bytes are unchanged.
The existing bounded ZIP parser independently rereads every regular member and
all member hashes agree. This dataset has only regular files; symlink/submodule/
LFS transport attacks remain unexecuted, not implicit PASS. No runtime installed
authority, successor accepted instance, full DAG or qualification follows from
these retained real input probes.

Current runtime correction: Git resolver now independently reads the repository
object format and validates both resolved commit and tree IDs against SHA1/40 or
SHA256/64; intermediate 41..63 lengths and mismatched tree formats reject. Eleven
targeted controls plus five existing real-Git source tests pass. This removes
length-only algorithm validation, but does not add independently pinned profile
authority selection: the local repository path is still supplied by the caller.
The resolved algorithm is a verified repository property, not proof that the
selected installed authority permits that repository/algorithm. Existing LFS
materialization regression verifies BOUNDED_SOURCE for an unresolved pointer;
complete source eligibility and special transport/runtime acceptance remain open.
Earlier 561-test history/workflow evidence predates this source resolver delta;
reuse only for paths independent of the changed resolver, and run affected source
consumers separately. Earlier standalone output is preserved as historical code
evidence; current output requires a separate build result.

Current affected consumer run: 63 PASS for stage1/stage2/stage3 and workflow
scope baseline, exact inputs in AFFECTED_RUNTIME_REGRESSIONS.json. New separate
build records current standalone bytes/self-test/help. OD-032 resolves producer
symlink target encoding versus closed successor schema: retain exact base64 raw
target, require explicit encoding/length/digest. Twenty-one controlled materializer
branch/schema controls PASS, including non-UTF8 target bytes and missing/wrong
fields. Input command responses are controlled, not authenticated actual trees.
Current schema also validates all retained 499 actual regular-source entries,
without repeating unchanged member materialization. Schema alone does not enforce
canonical base64 reencoding or independent target/raw length/digest reconciliation;
trusted source selection, special-member transport and durable guards remain open.

OD-033 now pins the parser entrypoint, exact code and complete dependency code
refs, the selected manifest-entry/path profiles and every operational quota. The
separate source parser preserves original ZIP metadata and verifies names, type,
mode, expanded raw bytes, length/digest and canonical symlink target bytes. Generic
NF02 ZIP parsing remains unchanged and still rejects symlinks. Thirty-five targeted
parser regressions PASS; real retained 499 regular members also pass current parser.
The earlier 91-test affected run binds its unchanged captured inputs with zero
drift; later archive budget-only changes are covered by the current 35 regressions.
Runtime records are append-only per run after correcting a diagnostic filename
collision. The overwritten 63-test diagnostic is not claimed as preserved byte
evidence; its observed result is superseded by the retained broader 91-test run.
No accepted SourceIdentity/Generation/manifest instance or installed profile is
created. Parser supports only regular/symlink complete input; unsupported required
LFS/submodules/other source types reject, never silently vanish or gain complete
eligibility. SourceMaterialization is caller input to a pure reconciler, not an
authentication token. Exact independently selected profile adapter, full typed
bootstrap instance closure, source alias mapping and durable admission remain open.
## Snapshot identity branch correction — 2026-10-08

Complete Data 8.1 separates authorized snapshot identity from Git identity.
The inherited Git-required conditional had no converse: a snapshot body could
carry either or both Git commit/tree fields. The pre-fix successor schema accepted
that hybrid. SourceIdentity/2 now forbids both fields in its snapshot branch;
the historical /1 schema remains unchanged. Three exact controls cover each field
alone and their pair. Forty-five source representation controls pass.

This closes the body-branch representation omission under OD029. It does not
establish a snapshot authority, supply a snapshot materializer, reconcile source
bytes, or qualify source acceptance. Exact selected authority/profile/algorithm,
source alias mapping and durable acceptance obligations remain open.

