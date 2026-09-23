# CURRENT MISSION — Run101 Candidate Validation

Base: Run100 Studio Workspace (validated source-of-truth).
Candidate: Run101 Media Reliability.
Branch: candidate/run101-media-reliability.

Single macro-area: P0 core media reliability.

Changes are limited to deterministic FFmpeg/FFprobe binary selection, bounded FFprobe failures, and ensuring import/proxy/export/output verification use the same validated media runtime. UI, R6, AI/OCR/Whisper and packaging are intentionally unchanged.

Promotion rule: do not move main until candidate CI passes real fixture generation, probe, corrupt-input failure, timeout failure, proxy generation, export, output probe and decode smoke.
