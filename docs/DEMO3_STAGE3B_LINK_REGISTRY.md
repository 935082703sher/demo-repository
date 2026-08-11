# Demo 3 Stage 3B Link Registry

The registry is server-owned and keyed by stable identifiers. A runtime lookup returns a URL only when the exact entry is active, runtime-eligible, approved, language-compatible, and known. Unknown identifiers and cross-language mismatches return no link; generated text cannot supply a URL.

The Stage 3B seed has 13 reviewed official URLs supplied in the implementation instruction. Every entry records ID, URL, language applicability, purpose, owner placeholder, approval state, verification timestamp, review-due timestamp, active state, runtime eligibility, and test-only state.

All seed entries are:

```text
approval_status = pending_review
active = false
runtime_eligible = false
test_only = true
```

Consequently none can be presented as an approved runtime link. The listed owner is a role placeholder, not a named approval. A later decision must be bound to the exact entry/version or content hash and language; it must not be a blanket approval.

Inventory URLs:

- `https://rtmc.uz/`
- `https://rtmc.uz/contact`
- `https://rtmc.uz/contact/faq`
- `https://rtmc.uz/contact/send-appeal`
- `https://rtmc.uz/opendata/phone-codes`
- `https://uzimei.uz/?id=instructions`
- `https://uzimei.uz/knowledge`
- `https://uzimei.uz/tariffs`
- `https://uzimei.uz/contacts`
- `https://mnp.uz/`
- `https://mnp.uz/ru`
- `https://www.mnp.uz/en`
- `https://lex.uz/docs/3336169`
