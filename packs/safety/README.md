# safety

**Three deterministic guards against the most common catastrophic failures.**

Unlike CLAUDE.md principles (probabilistic, can be overridden under pressure), these
hooks fire at the tool-call layer before the action executes.

### dangerous_bash_guard

Blocks `rm -rf /`, `rm -rf ~`, `rm -rf *`, `git push --force` to main/master,
`curl | bash`, `eval $(...)`, fork bombs, `chmod -R 777 /`, `dd` to block devices,
and `git reset --hard`. The single most-cited hook in every Claude Code community
collection.

### self_modification_guard

Blocks Write/Edit calls that target `~/.claude/hooks/` or `~/.claude/settings.json`.

The specific threat: a prompt injection embedded in a webpage or document tells Claude
to rewrite `credential_guard.py` to do nothing — then sends commands that leak your
credentials. This hook makes that structurally impossible within a session.

Narrower than "protect all `.env` files" (credential_guard from the `guardrails` pack
already handles credential reads). This guard closes the self-disabling attack surface.

### prompt_injection_scanner

PostToolUse hook on Bash/Read/WebFetch. After external content is fetched, scans it
for injection patterns:
- Instruction overrides ("ignore all previous instructions")
- Persona hijacks ("you are now jailbroken")
- Exfiltration commands ("send this data to attacker.com")
- Fake prompt delimiters (`###SYSTEM:`, `</instruction>`, `[INST]`)
- Base64-encoded versions of the above
- Unicode directional overrides (invisible injection text)

Cannot block (PostToolUse fires after the fact), but injects a WARNING into model
context so Claude knows to treat the content as untrusted data. Most effective against
adversarial content in web pages, emails, and external files.

## Contract

- **Installs** three scripts at `~/.claude/hooks/`
- **Registers** them in `~/.claude/settings.json` (merges, never overwrites)
- **Proves** each blocks known-dangerous inputs and allows harmless ones

## Iron Laws

- The self_modification_guard makes hooks immutable for the session's lifetime. If you
  need to edit hooks, do it from a fresh session (not while Claude is running).
- The prompt_injection_scanner is advisory — a sufficiently novel injection pattern may
  slip through regex. It's one layer of defence, not the only layer.
- Fail-open: all three hooks wrap logic in `try/except` so a parsing error never blocks
  legitimate tool calls.

## Anti-Patterns

- ❌ Installing without `guardrails` — this pack supplements it, doesn't replace it.
  Credential reads still need `guardrails` / `credential_guard`.
- ❌ Expecting the injection scanner to catch everything. Novel patterns, non-English
  injections, and carefully-crafted obfuscation can evade regex. Pair with good
  system-prompt hygiene and the `post_compact_reinject` hook from `context`.

## Related packs

- [`guardrails`](../guardrails/) — credential read guard, must run first
- [`context`](../context/) — post-compaction re-inject (paired defence against
  injection-induced rule amnesia)
- [`foundation`](../foundation/) — seeds the soft constitution that these hard hooks
  backstop
