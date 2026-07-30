# Demo 2 Approved-Knowledge Boundary

No official RTMC FAQ corpus was supplied for Demo 2. The committed records remain
unmistakably synthetic fixtures and must not be deployed as citizen knowledge.

## Required approved record metadata

A production-approved candidate must include:

- stable document ID, source title, language, category, content, and retrieval keywords;
- HTTPS source URL and version;
- `status: approved`, `approved: true`, `active: true`, and `synthetic: false`;
- non-empty `approved_by` and an approval timestamp;
- a `valid_from` timestamp and optional `valid_until`/`expires_at`;
- the lowercase SHA-256 hex digest of the exact UTF-8 content.

Retrieval excludes a record when approval, activity, validity, source, language,
category, or hash checks fail. Content is never auto-corrected or partially imported.

## Synthetic fixture rules

A demo-only record must use `status: demo_only`, `approved: false`, and
`synthetic: true`. Its content must visibly contain the appropriate demo warning.
It may demonstrate retrieval mechanics but is not an official fact.

## Validation procedure

Validate a candidate file before replacing any configured knowledge path:

```bash
python -m app.services.knowledge_import /path/to/candidate.json
```

Exit status is:

- `0` when every parsed record is eligible;
- `1` when JSON or schema parsing fails;
- `2` when parsing succeeds but one or more records fail policy eligibility.

The report contains IDs and counts only; it does not echo source content.

Content owners must review and approve the source file outside this tool. Passing
technical validation is not organizational approval. The application loads only the
explicitly configured file and sends only the top relevant eligible passages—not the
whole repository—to the provider.
