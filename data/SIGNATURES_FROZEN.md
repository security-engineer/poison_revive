# Signatures frozen (v1.1)

- File: data/signatures.jsonl, 1348 cases, written by 8 independent annotator agents from the poison text only (spec: data/SIGNATURE_SPEC.md).
- v1.1 change (made before any experiment output existed): AmapMap "+25" expression forms added.
- Validation against MCPTox labeled turn-1 responses (28,570 responses, 13 local + 15 online models): see data/signatures.validation.json.
- Known limits:
  - 4 text-only cases have malicious=[] and are excluded from Y.
  - About 18 cases have MCPTox reference responses that match the Chinese risk description rather than the current poison text, which suggests the responses came from an older poison version. Signatures follow the current text, because that is the stimulus our models see.
- sha256: 72a860b2c4cde8001b34c298ead27c4bd4a3295daad01e31407bdfa4b219dddb
