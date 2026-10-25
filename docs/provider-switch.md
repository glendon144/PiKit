# Inference providers

Open **Tools → Inference Provider…**, choose Baseten, Local, or Third-party,
enter the base URL (including the API prefix, usually `/v1`), model and API
key, then click **Save and select**. Saving immediately replaces the command
processor's inference client. An already-running request may finish on its
original provider. Local endpoints can use an empty key.

Settings and the selection survive restart in
`~/.config/pikit/providers.json`. This file contains saved keys in plaintext,
with owner-only permissions (`0600`); a newly created configuration directory
uses `0700`. It lives outside the checkout and must not be committed or shared.
The key field is masked. Saving is atomic; a failed save leaves the active
provider and previous settings unchanged. Saved values override environment
defaults. A saved empty local key intentionally overrides the environment.

Before a provider is saved, these environment defaults apply:

| Provider | Base URL | Model | Key |
|---|---|---|---|
| Baseten | `BASETEN_BASE_URL` | `BASETEN_MODEL` | `BASETEN_API_KEY` |
| Local | `PIKIT_OPENAI_BASE_URL` | `PIKIT_MODEL_NAME` | `PIKIT_OPENAI_API_KEY` |
| Third-party | `PIKIT_CUSTOM_BASE_URL` | `PIKIT_CUSTOM_MODEL` | `PIKIT_CUSTOM_API_KEY` |

Baseten remains the initial selection for compatibility, with
`https://inference.baseten.co/v1` and `openai/gpt-oss-120b` unchanged.
`OPENAI_API_TIMEOUT` remains supported. Local defaults to
`http://localhost:8081/v1`; replace `local-model` with your server's model ID.
Third-party URL and model must be explicitly configured.

Missing credentials no longer prevent opening the GUI. Requests report
configuration, authentication, connection, timeout, or HTTP errors without
printing credentials or remote error bodies. Unknown/corrupt saved selections
block inference until repaired in the dialog. There is no provider fallback.

## Investigation and reuse (2026-10-25)

The active path is `main.py` (also `pikit.py`) → `AIInterface` →
`CommandProcessor.ai` → GUI ASK/DISTILL and related document operations.
Previously `modules/ai_interface.py` selected Baseten through environment
variables only, created an OpenAI SDK client at startup, and failed startup
without its key. Its chat, stream, query and compatibility aliases are retained.
The alternate `local_ai_interface.py`/`localai_interface.py` files were not
wired into this launch path. No active selector or selection persistence was
present in this checkout.

On Blues, `/home/gross/git/PiKit.git`, HEAD `2071e85d`, contained the same
Baseten adapter. The accessible Dream Communicator repository was
`/home/gross/git/github-glendon144-mT3qsFa8/AI_Dream_Communicator_Deluxe.git`.
Its sidecar uses the FunKit name and contains:

- `FunKit/modules/provider_registry.py`: provider records, environment key
  references, persisted selection, and label lookup.
- `FunKit/modules/provider_dropdown.py`: readonly Tk combobox and provider
  change callback.
- `FunKit/modules/provider_switch.py`: an older in-memory switch.

The new registry and editor adapt the first two implementations' registry API
and label/combobox pattern to this smaller application. They retain PiKit's
existing SDK request adapter instead of adding another HTTP transport. The
sidecar's silent default-provider fallbacks, CWD-relative settings, placeholder
Baseten endpoint and separate global switch were deliberately not copied.

## Verification

Run `python3 -m pytest test_sidebar_buttons.py test_provider_gui.py test_providers.py -q`
with desktop access for Tk. Tests cover real SDK request construction through a
mock HTTP transport, all three endpoint routes and authorization headers,
stream routing, persistence and private permissions, Baseten defaults and
configuration preservation, failed-save rollback, malformed settings,
credential-safe errors, and the actual GUI save/client replacement flow.

The pre-existing automated sidebar tests pass. Other root test/demo scripts
are interactive GUI or database utilities, not an automated regression suite;
the bundled Python source and vendored environments are excluded.

No local server responded on ports 8081, 8080, 8000, 1234 or 11434 during
verification, so a real local model completion could not be performed. No
paid Baseten or third-party completion was made; their routing/configuration
was verified with test credentials and a mock HTTP transport.
