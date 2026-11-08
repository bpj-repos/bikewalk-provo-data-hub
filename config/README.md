# Configuration

`vercel.json` is copied into assembled publication staging. The whole repository is never the upload source.

`paths.example.json` documents the default private workspace locations. Copy it to ignored paths.local.json only when local locations differ. Relative values resolve from the hub root. The restricted path-map.json records old absolute origins and current relative destinations. Keep that map with the private workspace when backing up or restoring.
