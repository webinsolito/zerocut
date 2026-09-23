# CURRENT MISSION — Run104 Windows Core

Base: validated Run103 Concurrency Safety.
Candidate: Run104 Windows Core.
Single macro-area: real Windows core filesystem/state certification.

The Windows GitHub runner must import and compile the .pyw, persist/recover project state on NTFS, handle Unicode paths, reject traversal and perform revision-guarded atomic replacement.

This certifies a real Windows OS CI environment, not the user's physical PC/GPU.
