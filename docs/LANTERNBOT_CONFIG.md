# LanternBot configuration

LanternBot uses the machine's native Pi runtime internally. Provider/model policy is
scoped by the **actual WebSocket client IP**:

- `127.0.0.1` / `::1` -> `localhost`
- every other client IP -> `lan`

Lantern does not trust `X-Forwarded-For` for this decision.

The recommended default is **localhost = full native Pi inventory** while LAN is
filtered or locked independently.

```yaml
lantern_bot:
  enabled: true

  access:
    localhost:
      provider_mode: all          # all | whitelist | blacklist
      providers: []
      model_mode: all             # all | whitelist | blacklist
      models: []
      bypass_models: []
      selection:
        # null/null = inherit whatever provider/model native Pi is using.
        provider: null
        model: null
        lock_provider: false
        lock_model: false

    lan:
      provider_mode: whitelist
      providers:
        - "cliproxy-*"

      model_mode: whitelist
      models:
        - "cliproxy-2080/gpt-6.1-sol"
        - "cliproxy-2080/gpt-6-luna"

      # Bypasses the provider/model list filters only.
      # A hard selection lock below always wins over bypass_models.
      bypass_models:
        - "github-copilot/gpt-5"

      selection:
        # Optional LAN default. null/null keeps the current allowed Pi model.
        provider: "cliproxy-2080"
        model: "gpt-6.1-sol"

        # Set both true to hard-lock LAN to exactly the pair above.
        lock_provider: false
        lock_model: false

  policy:
    # null = unlimited. Enforced server-side and persisted per local day.
    max_prompts_per_day: null
    max_tokens_per_day: null

  greeting: >-
    🦸 Tôi là LanternBot — một thành viên của biệt đội Lantern.
    Ở đâu có Lantern, ở đó có ánh sáng; file nào tối nghĩa cứ đưa đây, tôi soi cho.

  lantern_context: |-
    You are LanternBot, the assistant embedded in Lantern.
    The newest <lantern_context> block is authoritative.
```

## Provider/model modes

`provider_mode` and `model_mode` are independent:

- `all`: do not filter that dimension.
- `whitelist`: only matching entries are allowed.
- `blacklist`: matching entries are denied.

Provider entries are glob patterns such as `cliproxy-*`. Model entries can be either
fully-qualified `provider/model` patterns or bare model globs such as `gpt-*`.

`bypass_models` can cross both provider and model list filters. It **cannot** cross
`lock_provider` or `lock_model`.

## Hard-locking LAN

To force LAN users onto one exact model:

```yaml
lantern_bot:
  access:
    localhost:
      provider_mode: all
      model_mode: all
      selection:
        provider: null
        model: null
        lock_provider: false
        lock_model: false

    lan:
      provider_mode: all
      model_mode: all
      selection:
        provider: "cliproxy-2080"
        model: "gpt-6.1-sol"
        lock_provider: true
        lock_model: true
```

The backend validates the locked model against Pi's live
`get_available_models` inventory. If it is unavailable, LanternBot reports the
configuration error instead of silently falling back.

## Native defaults

When a scope has no configured provider/model, Lantern does not pass a hardcoded model
to Pi. The native Pi provider/model on that machine is inherited as long as policy
allows it. This is why FJP can naturally use `cliproxy-2080`, while another machine
can naturally use GitHub Copilot without changing Lantern code.

If the inherited native model is forbidden by that scope's policy, LanternBot switches
to the first allowed model before accepting the prompt.

The browser selector is only presentation. Provider/model filters, locks, prompt
limits and token limits are enforced server-side for every chat command.

Selected file chips in the Lantern file manager are sent only inside
`<lantern_context>` as attachment paths; they are not copied into the visible user
message or loaded wholesale into the prompt.
