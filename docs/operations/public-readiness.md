# Public contribution readiness

Reviewed November 11, 2026. **Public launch is blocked pending the actions below.** The repository is private. Detailed matches, GitHub metadata, original archives, extracted files and verification logs are retained in the ignored private/reviews/2026-11-11-public-readiness directory. This guide contains no original private records.

## Completed preparation

Original code and associated original documentation have an MIT license. CONTRIBUTING.md gives a synthetic example, tests, PR expectations and dataset/third-party exceptions. SECURITY.md directs sensitive reports to the organization's verified contact address. Contributor Actions run on pull_request with read-only permissions and no persisted checkout credentials or private artifacts. The complete maintainer suites remain separate from the simple standard-library example.

GitHub ruleset 27062669 is active for main. It requires one approval and code-owner review and dismisses stale approvals. It blocks deletion and force pushes. The sole always-bypass actor is the individual owner @brycepj. Other contributors need the owner's approval, and the owner retains unrestricted merge/direct-push rights and can merge the owner's PRs without review. CODEOWNERS assigns every path to that owner. The preparation uses the owner's account. Future contributors submit PRs from their own accounts.

Monthly Safe Routes processing moved to the local LaunchAgent described in bicycle-stress.md. A live provider acquisition/model run completed, and its 1.3.1 private candidate independently reproduced every package byte. The schedule is installed for 7:41 a.m. Mountain on the first of each month. Its guard requires a clean main checkout. Private work in a shared checkout can delay execution and requires a manual retry. An independent backup and a continuously available Mac remain operational dependencies.

All seven GitHub release assets and seven Actions artifacts were retained locally with matching remote SHA-256 hashes. Every archive was restored into a fresh private directory and its extracted file bytes compared with the archive. The restored 1.3.0 Actions candidate passed the normal publisher's verify-only gate and independent rebuild. Future acquisition and publication use local checksummed archives. GitHub originals are retained for the separately reviewed launch cleanup.

## Exposure review and remaining launch actions

1. Preserve the verified backups in independent owner-approved private storage before retiring GitHub copies. The current recovery rehearsal used this disk and account. Off-machine coverage is unverified.
2. Remove or relocate private GitHub release attachments, review artifacts, run logs and summaries after retention is confirmed. Four source-receipt releases, seven artifact archives and seven historical runs were examined. Provider source snapshots, model inputs and unreviewed diagnostic leads must not become a public repository's implicit downloads. Remote deletion requires its own owner decision.
3. Confirm redistribution rights for the retained third-party crash manuals and HTML references, including frozen copies. Public availability and a code license do not establish permission to republish them. Resolve any disputed material before making the history public. Dataset version manifests retain their existing source-specific terms, including CC0, ODbL and CC BY where stated.
4. Complete the linked GitHub Projects review using read:project access. The current CLI credential lacks that scope. The browser is signed out. Board visibility, draft items, collaborators and workflows remain unverified.
5. Recheck public-only protections at launch. Enable secret scanning, push protection, dependency alerts and private vulnerability reporting where available. Confirm fork PR approval policy, permit public fork contributions, and inspect any inherited organization Actions policies. A private repository's current API responses cannot verify those future settings.
6. Review the historical home paths and public crash disclosure choices with the owner. The history includes source-qualified identifiers and mapped coordinates in previously approved packages, plus machine paths in provenance/recovery instructions. The map method documents rounding and source scope. No new withdrawal was requested and the ledger contains none. If a path, identifier or reference needs removal from history, preserve recovery evidence and obtain the separate history-rewrite decision.

The automated scan examined reachable Git file blobs and downloaded GitHub evidence, including extracted PDF text, structured CSV/GeoJSON fields, gzip GeoJSONs and archive members. Checked credential patterns produced no private-key, provider-token, credential-assignment or SSN-shaped matches. Hits for personal-field names occurred in schemas, normalization code, manuals and provider source metadata. Email hits in code were public request contacts or synthetic test values, and commit-author addresses were treated as metadata. The phone-shaped matches were numeric provider fields. Home paths require contextual review. This is a focused pattern and field review, with no OCR of scanned images and no complete semantic proof over every free-text value or binary OSM extract.

Remote refs showed main and four receipt tags, with no PR refs. No Git LFS configuration or pointers were found. GitHub reported no issues, PRs, issue/PR/commit comments, repository secrets, variables, environments, webhooks or deploy keys. A wiki Git lookup returned repository-not-found, which establishes no accessible wiki rather than clearing any inaccessible history.

## Settings review

| Setting or surface | Observed result and follow-up |
| --- | --- |
| Main and owner rights | Active PR/code-owner review rules, stale approval dismissal, deletion/force-push protection, individual owner always-bypass. Keep CODEOWNERS on main. |
| Collaborators | One direct collaborator, @brycepj with admin. Organization-inherited access should be rechecked as membership changes. |
| Forks | Repository private and allow_forking false at audit time. Public visibility changes fork behavior. Verify public contribution access at launch. |
| Actions | Enabled, all actions allowed. Default token read-only and unable to approve PRs. Contributor workflow pins checkout/setup-python commits. Consider restricting allowed actions after checking organization-wide usage. |
| Security features | Secret scanning/push protection, Dependabot alerts and updates disabled. Private reporting API returned 404. Availability and enablement remain launch checks. |
| Installed apps | Organization Vercel installation covers all repositories. Render installation selects repositories, but its exact selection for this repo was unavailable with the current user token. Review app installations with the owner. |
| Vercel project | No Git repository link. Deployments use the explicit staging/promotion pipeline. Fork protection enabled and SSO protects deployments except custom domains. Root/build/output settings use defaults. Keep uploads restricted to the catalog's assembled output. |
| GitHub deployments | No deployment records or environments. Vercel's separately verified project is the owning deployment surface. |
| Linked Projects | Unverified due to missing read:project and signed-out browser. |

## Dead code and artifact review

Removed the retired Actions candidate download path, private GitHub release uploader, direct-main publication commit/push helper, and obsolete map-publication parameters/constants. Release preparation now writes a reviewed package and ledger on a branch, while promotion consumes the recorded package from current main.

Retained the root compatibility scripts because the canonical Projects updater calls adopt_routes.py and recovery docs use update_crashes.py. The synthetic counts builder supplies tested release-integrity fixtures. Frozen historical code, duplicate manuals and reference captures preserve hashes and recovery evidence. The static review found 14 unconfirmed function candidates in the acquisition library, judgment, registry and checksum helpers. No dependable caller evidence justified removing those public/internal capabilities. The private ledger records their names for a future focused review. macOS AppleDouble metadata inside old archives was identified as metadata rather than malformed JSON. Original archives were preserved.

Pinned dataset resources, release manifests, baseline pins and the ledger are unchanged by this preparation. The code and configuration changes require the contributor checks and both maintainer suites. The private verification directory records exact results, including any unavailable-input skips.

## Verification evidence

The maintained local run passed 47 hub tests and 144 crash tests with no reported skips. A fresh clone passed the synthetic build/validation and its focused tests, then passed all 47 hub cases with eight private-input skips and all 144 crash cases with one private-receipt skip. GitHub Contributor checks also completed successfully on Linux.

The local monthly acquisition generated a private 1.3.1 candidate against the approved 1.3.0 predecessor and independently rebuilt it. The restored approved 1.3.0 candidate passed the publisher's verify-only operation. Local backup tests cover identical retries and rejection of archive corruption. Publication regressions exercise release preparation, refusal to promote an unrecorded release and retries after a staged verification failure. The new private candidate requires a separate dataset review.

Seven historical Actions logs and the retained review Markdown/JSON were examined. Rendered step-summary pages were unavailable through the current API/browser access. Treat removal or private relocation of the entire historical runs as the launch remedy for that remaining surface. The new contributor workflow's logs contain test output and visible skips, and upload no artifacts.
