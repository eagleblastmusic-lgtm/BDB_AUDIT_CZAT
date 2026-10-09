# Required future runtime delta

Approved R5.4 bytes govern later implementation. No runtime files were edited by N1–N4.

## N5

Components: `src/bdb_audit/core/registry.py; schemas/binding.py; schemas/orchestration.py; history/store.py; history/authority_hooks.py`.

Observed difference: Current /1 NF02 extension rows use PROVENANCE/PROPOSAL and bypass normative Registry legality.

Required change: Load exact R5.4 Registry/SchemaRegistry pins; no NF02 overlay. Implement FACT binding/1 unique-by-exact-assignment acceptance, prior-only refs, exact retry/CAS, raw/history atomicity; leave historical /1 read-only.

## N6

Components: `src/bdb_audit/workflow/packaging.py; workflow/assignments.py; workflow/package_resume.py; workflow/manual_stage.py; execution/adapters.py; history/raw_artifacts.py`.

Observed difference: Current package metadata/job context does not establish accepted immutable package authorization.

Required change: Finalize exact profiled package after accepted A; store durable raw; accept B in its own commit; separate later STARTED; deliver only reverified retained raw. Semantic checksum stays distinct from ZIP RawDigest. No retrospective B or DeliveryReceipt.

## N7

Components: `src/bdb_audit/workflow/result_proposal.py; history/authority_hooks.py; history/raw_artifacts.py; workflow result intake/normalization/completion consumers`.

Observed difference: Current /1 evidence copies attempt/source/history and compares result/package self-claims; /1 result bodies and security metadata differ from closed R5.4 bodies.

Required change: Construct exact E/2 from authenticated operation using prior A/B and frozen result slot; derive package context from B/A; retain result raw. In a later commit construct R/2 as exact Normalize(Q); enforce all ref/schema/profile equality and slot uniqueness. Runtime capabilities may enforce calls but are absent from canonical bodies and replay.

## N8

Components: `src/bdb_audit/core/registry.py; schemas/binding.py; schemas/bootstrap.py; history/store.py; workflow campaign open/create/bootstrap and version selectors`.

Observed difference: Current process-generated schema/extension paths and legacy/current context selectors are not the prepared R5.4 installed authority.

Required change: Authenticated qualified initial pins and legal genesis only for new campaigns; verify frozen executable bytes/digests offline before first acceptance. No latest-installed fallback, generic upgrade, old campaign write, /1→/2 mapping or retcon. Existing campaigns retain their own schema sets/read-only historical NF02 display. Missing/corrupt authority fails closed.

N9 adversarial qualification, N10 complete NF02 qualification and N11 full application start/create/package/delivery/result/completions/report/restart/recovery/continue with corruption and missing-object paths remain mandatory and NOT_RUN.
