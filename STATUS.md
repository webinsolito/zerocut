# ZeroCut Gaming AI — Source of Truth Status

Recovered and hash-verified on 2026-09-23.

## Verified baseline
- Candidate: `src/ZeroCut_Run100_Candidate_StudioWorkspace.pyw`
- SHA-256: `66e756d74b1eaa66eea9446c09db5062bdcc8a55c893ee2d33c51105c9520d30`
- Rollback: `rollback/Run99_FocusWorkspaceUX.pyw`
- SHA-256: `05772979e0619290680a108197cc7fa0a1d6d499c9d6ae835311bbcfeca4d263`
- Report: `reports/Run100_StudioWorkspace_TEST_REPORT.json`

Run101 is blocked until this recovered source-of-truth commit passes the repeatable smoke workflow.

## Scope of the smoke gate
Portable CI verifies exact hashes, Python compilation, safe module import and report/source consistency. It does not certify Windows, GPU, real FFmpeg hardware paths, native picker, preview, or export on the target machine.
