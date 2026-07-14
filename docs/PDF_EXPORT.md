# Export the guides to a single PDF

All guides are Markdown so they render on GitHub and export cleanly to PDF.

## Option 1 — pandoc (best quality)

Install pandoc + a LaTeX engine (e.g. `tectonic` or `wkhtmltopdf`), then run this **one-liner**
from the repo root (copy-paste to a bash shell / Git Bash):

```bash
pandoc README.md docs/ARCHITECTURE.md docs/SETUP_GUIDE.md docs/AWS_DEPLOY.md docs/ANDROID_BUILD.md docs/SAFETY_AND_BANS.md -o FridayUGC-Guide.pdf --toc --metadata title="Friday UGC — Framework & Guide" -V geometry:margin=1in
```

## Option 2 — HTML route (no LaTeX)

```bash
pandoc README.md docs/*.md -s --toc --metadata title="Friday UGC — Guide" -o FridayUGC-Guide.html && wkhtmltopdf FridayUGC-Guide.html FridayUGC-Guide.pdf
```

## Option 3 — VS Code / Cursor

Install the "Markdown PDF" extension, open any guide, right-click → "Markdown PDF: Export (pdf)".

## Option 4 — mermaid diagrams

`ARCHITECTURE.md` contains mermaid diagrams. GitHub renders them automatically. For PDF, use the
`mermaid-filter` pandoc filter, or preview in Cursor/VS Code and export from there:

```bash
npm i -g @mermaid-js/mermaid-cli mermaid-filter
pandoc docs/ARCHITECTURE.md -F mermaid-filter -o Architecture.pdf
```
