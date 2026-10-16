# LanternBot configuration

LanternBot uses the machine's native Pi runtime internally. By default it does **not**
force a provider or model: the provider/model already selected by Pi on that machine
is inherited.

```yaml
lantern_bot:
  enabled: true

  selection:
    # null = inherit the native Pi provider/model on this machine.
    provider: null
    model: null

    # Set either lock independently, or lock both.
    lock_provider: false
    lock_model: false

  policy:
    # Empty lists mean "do not filter the native inventory".
    allowed_providers: []
    allowed_models: []

    # Fully-qualified or glob patterns that bypass the allow lists.
    bypass_models: []

    # null = unlimited. Enforcement is server-side and persisted per local day.
    max_prompts_per_day: null
    max_tokens_per_day: null

  greeting: >-
    🦸 Tôi là LanternBot — một thành viên của biệt đội Lantern.
    Ở đâu có Lantern, ở đó có ánh sáng; file nào tối nghĩa cứ đưa đây, tôi soi cho.

  lantern_context: |-
    You are LanternBot, the assistant embedded in Lantern.
    The newest <lantern_context> block is authoritative.
```

Examples:

```yaml
# Inherit native Pi selection, but only expose selected models.
lantern_bot:
  selection:
    provider: null
    model: null
  policy:
    allowed_models:
      - "github-copilot/gpt-*"
      - "cliproxy-2080/claude-*"
    bypass_models:
      - "cliproxy-2080/gpt-6.1-sol"
```

```yaml
# Force and lock one model on a managed machine.
lantern_bot:
  selection:
    provider: "github-copilot"
    model: "gpt-5"
    lock_provider: true
    lock_model: true
```

Policy is evaluated against Pi's live `get_available_models` inventory. If a
configured/locked model is unavailable, LanternBot reports the configuration error
instead of silently falling back. If an inherited native model is excluded by policy,
LanternBot selects the first model allowed by the policy before accepting a prompt.

The browser selector never replaces backend enforcement. Provider/model locks,
allow-lists, prompt limits and token limits are checked server-side.

Selected file chips in the Lantern file manager are sent only inside
`<lantern_context>` as attachment paths; they are not copied into the visible user
message or loaded wholesale into the prompt. LanternBot reads a selected file only if
it is useful for the request.
