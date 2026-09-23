# CURRENT MISSION — Run102 Candidate Validation

Base: Run101 Media Reliability (validated on main).
Candidate: Run102 Project Recovery.
Branch: candidate/run102-project-recovery.

Single macro-area: P0 project persistence and crash recovery.

Run102 adds validated atomic project-state writes, last-known-good backup, corrupt-state quarantine, recovery from a fully-written interrupted temp file, stale-temp rejection and semantic state validation before commit.

Promotion rule: Run100 source-truth smoke + Run101 media regression gate + Run102 recovery integration must all pass. UI, R6, AI/OCR/Whisper, GPU and packaging are intentionally unchanged.
