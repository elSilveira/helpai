# Suapper Public Rename And Docs Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename public-facing branding to Suapper and refresh the docs homepage with the current feature set.

**Architecture:** Keep the site as a static React-in-HTML page under `docs/index.html`. Update public docs and metadata only; preserve internal Python module names and the existing `helpai` entry point for compatibility.

**Tech Stack:** Static HTML, inline React 18 UMD, inline CSS, Markdown, Python package metadata.

---

### Task 1: Update Docs Homepage Branding And Copy

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Update metadata**

Replace previous page metadata with Suapper metadata, including title, descriptions, keywords, JSON-LD name, canonical URL, social URLs, and repository URL.

- [ ] **Step 2: Update visible page content**

Change navigation, hero, preview labels, feature cards, privacy copy, setup commands, CTA, and footer to Suapper branding.

- [ ] **Step 3: Add current feature coverage**

Ensure feature cards mention auto whisper, cumulative screenshot context, separate code panel, Clear Context, Codex OAuth, and local/cloud provider choices.

- [ ] **Step 4: Verify docs page text**

Run: `rg -n "helpai" docs/index.html`

Expected: any lowercase `helpai` matches are intentional compatibility references only.

### Task 2: Update Static Site Metadata Files

**Files:**
- Modify: `docs/sitemap.xml`
- Modify: `docs/robots.txt`
- Modify: `docs/social-preview.svg`

- [ ] **Step 1: Update URL metadata**

Change the sitemap location and robots sitemap reference to `https://elsilveira.github.io/suapper/`.

- [ ] **Step 2: Update social preview**

Change preview accessible label and displayed product name to Suapper.

- [ ] **Step 3: Verify static metadata**

Run: `rg -n "helpai" docs/sitemap.xml docs/robots.txt docs/social-preview.svg`

Expected: no matches.

### Task 3: Update README And Package Display Metadata

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update README branding**

Change user-facing product references to Suapper and add current features from recent work: Codex OAuth, auto whisper, Clear Context, separate code panel, and cumulative screenshot context.

- [ ] **Step 2: Preserve compatibility notes**

Leave source folder, wheel name, console command, and module references as `helpai` where they describe current technical compatibility.

- [ ] **Step 3: Update safe package metadata**

Change `pyproject.toml` description and author display name to Suapper while leaving `[project].name`, `[project.scripts]`, and `py-modules` unchanged.

- [ ] **Step 4: Verify remaining old branding**

Run: `rg -n "previous-name public branding" README.md pyproject.toml docs`

Expected: no public-facing old branding remains, except compatibility references if explicitly explained.

### Task 4: Final Verification

**Files:**
- Read-only verification across changed files

- [ ] **Step 1: Inspect changed files**

Run: `git diff -- docs README.md pyproject.toml`

Expected: diff only contains public rename/docs refresh and no unrelated source code changes.

- [ ] **Step 2: Check working tree**

Run: `git status --short`

Expected: changed docs/metadata files plus existing `docs/superpowers/` planning files.
