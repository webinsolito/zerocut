# CURRENT MISSION — Run111 Whisper Certification

Base: validated Run110 OCR Certification.
Candidate: Run111 Whisper Certification.
Single macro-area: real local whisper.cpp inference.

The gate installs the pinned whisper.cpp binary and pinned tiny.en model, synthesizes spoken "Zero Cut" audio locally, requires semantic transcription, fingerprints exact binary/model SHA-256, then exercises ZeroCut's full media-to-transcript cache path.

Presence-only discovery is not a pass.
