# Graft — Independent Security Audit (Malicious Intent)

**Subject:** `@nanonets/graft` — local clone of https://github.com/trailhq/Graft
**Audited at commit:** `f9e6539` (branch `main`)
**Date:** 2026-09-14
**Intended use:** Claude Code in Windows Terminal, personal PC (Windows 10 Pro)
**Auditors:** Two independent passes — Claude Opus 5, then Claude Fable 5.1 with no
knowledge of the first pass's findings.

> **Scope note.** This is a *malicious intent / abuse* audit, not a vulnerability
> audit. The question asked was: *would installing and running this tool harm the
> user, exfiltrate their data, abuse their hardware, or betray their trust?* It is
> **not** an assessment of whether the code contains exploitable bugs.

---

## Verdict

**Safe to use**, with two disclosed behaviors worth knowing about (neither is
malicious; both are avoidable — see [Recommended settings](#recommended-settings)).

No malware. No obfuscation. No hidden exfiltration. No cryptocurrency mining or
wallet/clipboard hijacking. No reading of legal name, postal address, hostname,
username, SSH keys, browser data, or credential stores. No attacker-controlled
prompt injection.

Both audit passes reached this verdict independently.

---

## Method

Static source review. Both passes were instructed **not to trust `README.md`,
`TELEMETRY.md`, `SECURITY.md`, or code comments** — this project's prose is
unusually verbose and persuasive, which is also what well-disguised software looks
like. Every privacy claim in documentation was checked against the code that
enforces it.

Searched for: `fetch`/`http`/`https`/`net`/`dgram`/`WebSocket`; `child_process`/
`exec`/`spawn`/`execFile`; `process.env`; `homedir`/`os.userInfo`; filesystem reads
outside the project root; `eval`/`new Function`/`atob`/`Buffer.from(...,'base64')`.
Then followed every hit that touched network, subprocesses, or the environment.

---

## Findings by area

### 1. Malware, obfuscation, remote code execution — **Clean**

No `eval()`, `new Function()`, `atob()`, or base64-decode-and-execute anywhere in
`src/`. Nothing fetches and executes remote code.

The two `Buffer.from(..., 'base64')` hits are ordinary HTTP Basic-Auth header
construction and ID generation in `src/app/` — encoding, not payload decoding.

Initial greps for `eval`/`Function` produced hits in `format.ts` and `hooks.ts`;
a direct regex confirmed these were **false positives** matching substrings such
as "evaluate", not real calls.

### 2. Network destinations — **All disclosed, none hidden**

Complete enumeration of outbound destinations, with what each sends:

| Destination | What it sends | When |
|---|---|---|
| `events.nanonets.com/batch/` | Anonymous PostHog analytics: app version, OS, arch, Node major, command name (fixed enum), **bucketed** counts, language list | Background, ≤1×/day; fully gated |
| `registry.npmjs.org` | Package name only (`npm view` update check) | Background, ≤1×/day |
| `agents.nanonets.com` | Commit messages, PR titles/comments, filenames, symbol names/signatures/hashes, doc & config file contents (README, CODEOWNERS, ADRs) — **never raw source or diffs** | **Only** on explicit `graft brain push` |
| `api.github.com` | Your GitHub token, as a bearer to GitHub itself | **Only** on explicit `graft brain push` |
| LLM provider (Anthropic / OpenAI / LiteLLM / OrcaRouter) | Code to be summarized | **Only** if `GRAFT_API_KEY` is set, for `build --deep` |

Nothing fires without an install, a build, or an explicit opt-in command.

### 3. Resource abuse, mining, hijacking — **Clean**

No cryptocurrency, wallet, or clipboard code. Background child processes exist
only for: telemetry flush (1×/day, 8s timeout, detached), npm update check
(1×/day), graph auto-sync after an edit (lock-file bounded), and brain-rules
refresh (TTL-gated). All short-lived and timeout-bounded — **no persistent
daemons**, no unbounded loops.

### 4. Personal identity data — **Not read, not transmitted**

- `os.userInfo()` is **not used anywhere** in `src/`.
- No SSH key reads, no browser data, no credential-store access.
- `homedir()` is used only to *locate* `~/.graft/` and `~/.claude/settings.json` —
  not to derive identity.
- No legal name, postal address, hostname, username, or email is collected.

The only identity-adjacent read is a GitHub token (`gh auth token` /
`GH_TOKEN` / `GITHUB_TOKEN`) at `src/brain/push.ts:93`, used **only** as a bearer
against `api.github.com`, and **only** when you run `graft brain push`. It is
never sent to Nanonets.

### 5. Telemetry — **Documentation claims are enforced in code**

`TELEMETRY.md` makes strong privacy claims. Unlike most such claims, they are
enforced by the implementation:

- **`src/telemetry/contract.ts:39`** is a hard allowlist keyed by event. `track()`
  drops unknown events *and* unknown properties, so a careless future call site
  like `track('query', { path })` sends `query` with **no** `path`.
- **Every number is bucketed** — `"200-999"` files, never `417`. Exact counts plus
  a language set start to fingerprint a specific repo; buckets do not.
- **Every string is a fixed enum member.** `command` is one of eight; error `code`
  is one of eleven. A value outside the set is dropped — which is what stops a
  file path, symbol name, or error-message fragment from riding along inside a
  "string property".
- **`src/telemetry/gate.ts:64`** re-checks the gate before *every* append and
  *every* send. `DO_NOT_TRACK` outranks the tool's own setting.
- The PostHog key ships **empty** in source (`src/telemetry/key.ts`); it is stamped
  in at publish time by `scripts/stamp-telemetry-key.mjs` from a maintainer-only
  env var. A clone, fork, or local `npm run build` is therefore **inert**. *(A
  registry `npm install` does carry the key — see the correction note below.)*
- `graft telemetry debug` prints the exact outgoing JSON without sending it.

### 6. Prompt injection — **Clean; content is not attacker-controlled**

Graft installs Claude Code hooks that inject text into the agent's context each
turn. Assessment:

- `.claude/skills/graft/SKILL.md` is **static** guidance shipped in the repo, not
  generated from untrusted input. It is assertive about preferring graft over
  grep — self-promotional, but that is normal tool-usage guidance, not an attack.
- The `UserPromptSubmit` hook (`src/claude/hooks.ts:437-461`) injects `graft ask`
  results, which are **locators** (`file:line` pointers) drawn from *your own*
  indexed repository — deliberately not inlined source.
- The only route to adversarial injected content is if **your own repo already
  contains hostile text** that graft indexes verbatim (e.g. a malicious comment in
  a third-party dependency). That is inherent to any code-context tool and is not
  something Graft adds.

No mechanism was found for injected content to originate outside the local repo.

### 7. Install-time and CI behavior — **Clean**

- **No `preinstall` script exists.**
- `postinstall` (`scripts/postinstall.mjs`) records one anonymous `install` event
  (same gates as all telemetry), prints a one-line nudge, exits early under `CI`,
  and is wrapped so it can **never fail the install**.
- `prepare` runs the TypeScript build plus `stamp-telemetry-key.mjs`, which only
  rewrites a local `dist/telemetry/key.js` from an env var that is empty for
  anyone but the maintainer.
- GitHub Actions workflows are the **maintainers' own CI** — they do not run on
  your machine. They are written with real discipline: pinned action SHAs,
  `persist-credentials: false`, `pull_request_target` jobs that never execute PR
  code, and secrets scoped away from fork PRs.

### 8. Supply chain — **Clean**

All **100 lockfile packages resolve to `registry.npmjs.org`**. No git URLs, no
tarball URLs, no `http:` sources. No typosquats. Every dependency matches the
tool's stated purpose: tree-sitter grammars for the languages it parses,
`@anthropic-ai/sdk` / `openai` for LLM calls, `commander` / `dotenv` /
`gray-matter` for CLI and config, `d3-force` for the graph viewer, `tsx` /
`esbuild` / `node-gyp` as dev tooling.

Native C++ compilation at install time is limited to the tree-sitter grammars,
which is legitimate and expected for those packages.

---

## The two caveats

Neither is malicious. Both are disclosed behavior, and both are avoidable.

### Caveat 1 — It reads your Claude Code transcripts

`src/claude/tally.ts` reads the **last 1 MB** of your session transcript on every
turn end (the `Stop` hook). Traced end to end, it:

1. Regex-tests the text for a `"graft saved ~N tokens"` string (`TALLY` regex).
2. Increments one of two counters.
3. Separately sums token costs from `usage` fields for the statusline.

The prose itself is **never stored and never sent** — only a bucketed count
crosses the wire. That is genuinely what the code does.

It is nonetheless the most invasive behavior in the tool. If reading conversation
transcripts is over your line *regardless* of what is done with the content, that
is a legitimate reason to decline the hooks. **Avoided by:** `graft init --no-hooks`.

### Caveat 2 — `graft brain push` reads your GitHub token and uploads repo metadata

`src/brain/push.ts:93` shells out to `gh auth token` and uploads commit messages,
PR discussion, doc files, and symbol names to `agents.nanonets.com`.

Mitigations, both verified in code:

- It is a **manually typed command only**. Nothing in the hooks or CLI wiring
  triggers it automatically.
- It **requires a brain token** you must first obtain from Nanonets' site and
  paste via `graft brain connect`.
- It prints what it is about to do before doing it, including
  `"No file contents leave this machine."`
- The GitHub token is used as a bearer against **GitHub's own API**, not uploaded
  to Nanonets.

**Avoided by:** never running `graft brain connect` / `graft brain push`. The path
stays entirely dormant.

---

## Minor issue (not a security concern)

`.claude/helpers/graft-hooks.cjs:7` and `graft-statusline.cjs:7` both contain a
hardcoded absolute path from a maintainer's machine:

```
/Users/shrishdwivedi/Documents/Context graphs/context-graph-engine/dist/claude
```

It is tried first in a path-resolution fallback chain and silently fails on any
other machine, falling through to correct resolution. Harmless — but it leaks a
developer's local directory structure into a public repo. Worth reporting upstream
as a packaging hygiene bug.

---

## Recommended settings

```powershell
# Hard-gate all telemetry. Checked before every append AND every send;
# outranks graft's own setting unconditionally.
$env:DO_NOT_TRACK = "1"

# Optional: skip hooks to also avoid transcript reading (Caveat 1).
npx graft init --no-hooks
```

1. **Set `DO_NOT_TRACK=1`** in your PowerShell profile so it persists.
2. **Never run `graft brain connect` / `graft brain push`** (avoids Caveat 2).
3. **Leave `GRAFT_API_KEY` / `GRAFT_PROVIDER` unset** unless you want
   `build --deep`. Without them, `build` / `ask` / `grep` / `map` / traversal are
   fully local, deterministic tree-sitter operations with **no network calls**.
4. **Run `graft telemetry debug`** any time to print the exact payload that would
   be sent. It sends nothing.
5. **Consider `--no-hooks`** if transcript reading bothers you. You still get the
   CLI and MCP tools, which is the tool's actual value.

---

## Where the two passes diverged

Recorded for honesty about the process.

- **Pass 1 overstated the network surface.** Pass 2 established that `package.json`
  `files:` limits the npm tarball to `dist/`, `scripts/`, `README.md`, `LICENSE` —
  so all of `src/app/` (the GitHub-App/SaaS backend, where most `api.github.com`
  calls live) **never reaches a user's machine**. Pass 1's enumeration was correct
  about the *repo* but overstated what runs on *your PC*.
- **Pass 1 missed a destination.** `registry.npmjs.org` via `npm view`
  (`src/cli-meta.ts`), a daily update check. Benign — it sends only a package name.
- **Pass 1 did not check the dependency tree.** Pass 2 did; it is clean (§8).
- **Pass 2 did not separately flag the transcript read.** It reviewed
  `scripts/tally-audit.mjs` (a local-only diagnostic, no network) but did not
  surface `src/claude/tally.ts` as a caveat. This is a difference in emphasis, not
  a contradiction — Pass 1's finding stands and is recorded above as Caveat 1.
- **Correction to Pass 1's telemetry description.** Pass 1 said the PostHog key is
  "baked into published builds". More precisely: the key ships **empty** in source
  and is stamped in at publish time, so clones and local builds are inert — but the
  registry `npm install` you would actually run **does** carry it. Practical
  upshot is unchanged: set `DO_NOT_TRACK=1`.

---

## Limits of this audit

**Read this section before relying on the verdict.**

Both passes were **static source review of the current `main` branch only**.
Neither auditor:

- **Executed the tool**, ran `npm install`, or captured actual network traffic.
  No packet capture, no sandboxed execution, no strace/procmon.
- **Diffed the published npm tarball against this clone.** The build *process* was
  verified, but the artifact that would land on your PC was not independently
  rebuilt and compared byte-for-byte. **This is the largest remaining gap** — the
  code you install is built from this source, not proven identical to it.
- **Audited transitive dependency source.** The ~100 packages were verified to be
  the genuine, correctly-named registry packages — *not* that each is itself free
  of issues upstream.
- **Reviewed git history.** Only the current state at commit `f9e6539` was
  examined. A clean `main` does not prove a clean past, and it says nothing about
  future commits.
- **Assessed exploitable vulnerabilities.** Out of scope by design — this audit
  looked for malicious intent, not for bugs an attacker could abuse.
- **Fully audited `src/app/`.** Confirmed not shipped to users, so out of scope
  for a local-install threat model; its logic was not reviewed in depth.

### What this means practically

The verdict covers **this commit, as source**. It does not extend to future
versions. An `npm update` pulls code nobody in this audit has read — the standard
supply-chain exposure of any dependency, not something specific to Graft.

To close the biggest gap, diff the published tarball against this clone:

```powershell
npm pack @nanonets/graft
# then compare the extracted dist/ against a local `npm run build` output
```

---

*Audit performed 2026-09-14 by Claude Opus 5 and Claude Fable 5.1 at the user's
request. Two independent passes; the second had no knowledge of the first's
findings. Static analysis only — see [Limits](#limits-of-this-audit).*
