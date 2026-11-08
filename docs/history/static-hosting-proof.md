# Static hosting proof, November 7, 2026

The existing Vercel team brycepjs-projects hosts the dedicated bikewalk-provo-data-hub project. Two promotions used the stable alias https://bikewalk-provo-data-hub.vercel.app. Separate staging directories contained only vercel.json and public/. No framework build, functions, database, paid storage, seats or add-ons were added.

| Production deployment | Checks |
|---|---|
| dpl_66Q3PE56jtoCmVpi7w99PEtYjnfq | Eight anonymous HTTPS files matched the candidate. |
| dpl_CcMZnPXnSQyvNtMTjjYGW6qyAEvm | Sixteen files (8,048 bytes total) matched, including all original pins. CSV and JSON MIME types and wildcard CORS headers were checked. A PUT to /write-probe returned 404. |

Before and after promotion the November 1–7 team usage report showed $4.4672 effective and $0 billed. Billing can lag. The seven existing source CSVs total 17,651 bytes. Ten thousand complete copies would transfer about 177 MB before overhead. The published Pro Flat Rate CDN allowance is one million requests and 1 TB monthly, shared at the team level; verify current team terms before expansion. Review team usage at promotion and before adding larger datasets. Pause expansion near the applicable allowance and present projected overages to the owner. This proof added zero observed charges. [Vercel Pro plan](https://vercel.com/docs/plans/pro-plan)
