# Contributing

## Issues

Bugs and ideas go to [issues](https://github.com/Case211/remnawave-admin/issues). Useful things to attach to a bug report:

- the panel version (shown on the dashboard) and the agent version if the node is involved
- a slice of the logs around the problem
- what you already tried

## Pull requests

```bash
git checkout -b feature/name
# changes
git commit
git push origin feature/name
```

Then open a pull request. A change that arrives with a test is easier to accept: the test also explains what exactly was broken.

On your first pull request a bot asks you to sign the [CLA](https://github.com/Case211/remnawave-admin/blob/main/CLA.md) — one comment, and it is remembered afterwards.

## Documentation fixes

Every page has a "Suggest an edit" link at the bottom that opens the file straight in the GitHub editor. The sources live in `docs/`, the site is built by VitePress and published automatically on push to `main`.

The Russian version is at the root of `docs/`, the English one in `docs/en/`. If you change text that exists in both, change both: translations that drift apart are worse than a missing one.

## Licence

AGPL-3.0 with a plugin exception (§7). Versions up to and including 2.15.x remain under MIT. A commercial licence for proprietary use is available on request.
