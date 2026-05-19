# Suapper Public Rename And Docs Refresh Design

## Goal

Rename the previous public-facing project identity to Suapper and refresh the docs page so it reflects the current Windows overlay feature set.

## Scope

Update the public website, social metadata, sitemap/robots references, README copy, and package display metadata. Keep Python module names, imports, and the existing `helpai` console command stable in this pass so the rename does not become a packaging migration.

## Page Content

The docs homepage should present Suapper as a free, open-source, local-first Windows AI overlay for live calls, QA reviews, training, coding help, screenshots, and audio-driven assistance.

The page should call out the current features:

- Live transcript context and auto whisper suggestions.
- Screenshot analysis with cumulative context across related screens.
- Separate insight and code panels.
- Clear Context support for resetting saved model context.
- Local Ollama and faster-whisper path.
- Optional OpenAI, xAI, and Codex OAuth providers.
- Capture-safe overlay behavior and configurable settings/hotkeys.

The page should be ready to receive real screenshots later. Until those are available, the existing illustrated overlay preview can remain, but its labels and copy should use Suapper branding.

## Metadata

SEO, Open Graph, Twitter card, JSON-LD, canonical URLs, sitemap URLs, robots sitemap URL, and social preview text should use Suapper. Repository URLs should move to the expected `https://github.com/elSilveira/suapper` target for public-facing links.

## README And Project Metadata

README should use Suapper branding in user-facing text while explicitly preserving current source commands where they still use the old folder or command names. `pyproject.toml` should update package display fields where safe, but should not rename modules or scripts in this pass.

## Verification

Verify by searching for remaining previous-name mentions in `docs`, `README.md`, and `pyproject.toml`. Remaining `helpai` strings should be limited to compatibility commands, existing module/package identifiers, or paths that are intentionally unchanged for this pass.
