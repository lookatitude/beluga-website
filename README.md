# beluga-website

Source for [beluga-ai.org](https://beluga-ai.org): the documentation, blog and
marketing site for the [Beluga AI](https://github.com/lookatitude/beluga-ai)
Go agent framework.

Built with Astro 7, Starlight, React 19 and Tailwind v4. Deployed to GitHub
Pages.

## Develop

Requires Node 22.23.4 or later and Yarn 1.22.

```bash
yarn install --frozen-lockfile
yarn dev        # dev server at http://localhost:4321
yarn build      # production build into dist/
yarn preview    # serve dist/
```

Docs live in `src/content/docs/docs/`, blog posts in `src/content/docs/blog/`,
marketing pages in `src/pages/`. The sidebar is `src/config/sidebar.json`.
Redirects for moved pages are in `astro.config.mjs`.

## Framework API reference and reports

The Go API reference (`/godoc/`) and the changelog, security and code-quality
reports come from the `docs-bundle.tar.gz` attached to each framework release.
`scripts/fetch-docs-bundle.sh [tag]` downloads it (needs an authenticated `gh`
CLI). Without it the site still builds; the godoc pages 404 and the reports
show placeholder text.

## Checks

Pull requests run `.github/workflows/pr.yml`:

- `yarn build`, then `python3 scripts/check-links.py dist` (fails on broken
  internal links).
- A guard against the pre-v2 import path. Go imports must use
  `github.com/lookatitude/beluga-ai/v2/...`.
- An advisory Go snippet check, `scripts/snippets/check.sh <framework-checkout>`,
  which compiles the documentation's Go examples against the framework.

Run the snippet check locally against a framework checkout (needs Go 1.26+):

```bash
scripts/snippets/check.sh ../framework /tmp/snippet-report
```

## Deploy

Pushes to `main`, framework releases (`repository_dispatch`) and manual runs
deploy through `.github/workflows/deploy.yml`. See `AGENTS.md` for the full
deploy model, Starlight overrides and content rules.

## Related repositories

- [beluga-ai](https://github.com/lookatitude/beluga-ai): the framework
- [beluga-examples](https://github.com/lookatitude/beluga-examples): runnable examples

## License

MIT. See [LICENSE](LICENSE).
