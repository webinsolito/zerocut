# CURRENT MISSION — Run106 Timeline Reliability

Base: validated Run105 Windows Media Roundtrip.
Candidate: Run106 Timeline Reliability.
Single macro-area: fail-closed timeline edit validation.

Reject NaN/infinite/reversed/out-of-range/too-short/duplicate-ID/oversized timelines instead of silently coercing them. Invalid selected segment falls back to a valid segment.

Windows Run104/105 evidence remains preserved; this run uses Linux core regression plus timeline tests.
