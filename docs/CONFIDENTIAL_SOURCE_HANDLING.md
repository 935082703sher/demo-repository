# Confidential Source Handling

## Boundary

Departmental `.doc`, `.docx`, `.rar`, and PDF files are confidential inputs. They are
not repository assets, approved public knowledge, prompt material, or test fixtures.
Raw files and unique case text must never be committed, logged, quoted, pasted into
issues, or sent to an external provider.

The local confidential input directory must be outside the Git worktree and restricted
to the current user. In-repository paths for raw inputs, extraction, OCR, temporary
conversion, and local manifests are ignored as a second line of defense; operators
must not treat an ignore rule as permission to keep confidential material there.

## Required sequence

1. Place the unopened input in the restricted local quarantine directory.
2. Build a content-free manifest containing a source ID, filename, classification,
   and reviewed SHA-256 digest.
3. Verify a regular non-symlink file by streaming SHA-256 before parsing it.
4. Inventory archive metadata before extraction.
5. Reject traversal, absolute or duplicate paths, symlinks, encryption, executables,
   macros, nested archives, unexpected extensions, excessive sizes, and suspicious
   compression ratios.
6. Extract only into a new empty mode-`700` directory with the offline policy enforced.
7. Use an injected local extractor for document/PDF text. The policy model accepts
   only `network_access=false`.
8. Scan extracted text for likely names, addresses, phones/subscriber numbers, email,
   JSHSHIR, passport identifiers, IMEI values, document codes, and signatures.
9. Derive only generalized synthetic scenarios without direct quotations.
10. Scan the complete derived structure again. A finding fails the build and reports
    only category counts, never captured values.
11. Delete temporary extraction and OCR products after the reviewed derivation is
    saved and verified.

## Archive support

Stage 1 provides a shared archive-member policy and safe ZIP extraction for synthetic
tests. RAR content remains unopened. A reviewed, local-only RAR inventory/extraction
backend is required before a later stage may inspect the supplied RAR; failure to have
such a backend is a hard stop, not permission to use an online converter.

## Privacy-safe reporting

Transformation reports may contain source IDs, aggregate file counts, detected PII
categories, and pass/fail status. They must not contain extracted values, snippets,
raw chat, full paths, or case-specific filenames unless RTMC explicitly approves their
retention. PDF filename/hash manifests remain local and uncommitted pending approval.

## Provider and logging rules

- The default mock provider remains enabled for tests.
- No confidential extraction code invokes a provider or exposes a network option.
- Provider requests must never contain secure-field values or extracted confidential text.
- Exceptions and audit output use stable policy codes and source IDs only.
- Ordinary logs must not contain source text, message bodies, credentials, or PII.
