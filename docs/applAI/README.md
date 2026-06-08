# applAI Planning Hub

applAI is the planned job-application automation subsystem for HelpAI/Suapper. It will let the local agent use Playwright to navigate approved job sites, extract role information from HTML and screenshots, prepare application answers, and assist with applications using local Ollama models when possible.

The first implementation should be an assisted workflow, not an unrestricted bot. It should make browsing and extraction fast, keep credentials protected, and require clear user approval before high-impact actions such as account registration, password entry, email-token use, or final application submission.

## Planning Documents

- [Architecture](architecture.md) defines the subsystem boundaries, data flow, safety model, and major components.
- [Configuration](configuration.md) defines settings, allowlists, credentials, local Ollama, Playwright, and Gmail/email integration.
- [Implementation Roadmap](implementation-roadmap.md) breaks the work into buildable phases.
- [Security And Compliance](security-and-compliance.md) captures the rules that prevent unsafe automation, account exposure, or site abuse.

## Recommended Build Order

1. Build the Playwright browser worker with an allowlisted site registry and read-only navigation.
2. Add extraction from DOM text, page metadata, screenshots, and local vision models.
3. Add local profile/resume matching and application-draft generation.
4. Add guarded form filling with human confirmation before submission.
5. Add credential vault and Gmail token retrieval through scoped, structured commands.
6. Add durable job tracking, retry handling, and settings UI.

## Current Repo Fit

The existing project is a Python desktop app with:

- Local-first AI provider settings through Ollama and OpenAI-compatible clients.
- Screenshot capture and vision preparation.
- A local settings file and settings UI.
- Tests around provider behavior, settings, screenshots, and UI behavior.

applAI should reuse those patterns where practical, but it should live in its own package/module boundary so browser automation, account data, email access, and job records do not become tangled with the overlay hotkey flow.
