# Real environment gates

The source-truth CI is intentionally portable and cannot certify real Windows or GPU behavior.

Still requires real Windows validation:
- launching the .pyw/app;
- native file picker and Windows paths, including Unicode and permission cases;
- local FFmpeg/FFprobe discovery/bootstrap;
- real import, preview and export;
- project recovery after interruption/crash;
- output decode/probe and A/V sync.

Still requires compatible real hardware before any GPU claim:
- capability detection;
- encoder/decoder smoke test;
- repeatable benchmark against CPU fallback;
- output quality check;
- stability and CPU fallback validation.

A cross-platform CI PASS must never be reported as a Windows/GPU PASS.
