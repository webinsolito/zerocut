# ZeroCut Gaming AI — Source of Truth Status

Recovered, hash-verified and CI-validated on 2026-09-23.

## Verified baseline
- Candidate: `src/ZeroCut_Run100_Candidate_StudioWorkspace.pyw`
- SHA-256: `66e756d74b1eaa66eea9446c09db5062bdcc8a55c893ee2d33c51105c9520d30`
- Git blob: `67f2f156ffe9e64c85e3d451e912dc069cf7341b`
- Rollback: `rollback/Run99_FocusWorkspaceUX.pyw`
- SHA-256: `05772979e0619290680a108197cc7fa0a1d6d499c9d6ae835311bbcfeca4d263`
- Git blob: `eac21a770266ef8a6cd2f18b6c9594c97fa50efb`
- Report: `reports/Run100_StudioWorkspace_TEST_REPORT.json`

## Recovery gate
GitHub Actions run 35878436456: PASS.
Portable smoke checks exact hashes, report/source consistency, Python compilation and safe module import.

Source-of-truth recovery is complete. A distinct Run101 is now authorized only as the next separate cycle, with one P0 macro-area and its own rollback/tests.

## Not certified
This does not certify real Windows, GPU, hardware encode/decode, native picker, target-machine preview, or target-machine export.
