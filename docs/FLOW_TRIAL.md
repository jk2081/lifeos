# Frappe Flow trial (issue #108)

Question from the owner, 24–25 November 2026: can Flow do what Ask does, and "before we build more, should we move to Flow?"

**Short answer: use Flow as the engine, keep Life OS's own chat screen. Not now: after the gaps in section 5 are closed. Nothing changes for the owner today.**

## What was done

- Frappe upgraded from v16.56.0 to **v16.61.0** (CI, Docker bench, install guide). Flow ships in it. The unit suite passes on it; the acceptance walk runs in CI on the pull request.
- Flow Server started on the local bench (`bench flow-server status` says running, a Unix socket, under the bench's own process list; on a self-hosted server it runs under Supervisor).
- Model: a fake OpenAI-compatible server (`tools/fake_openai.py`, no key, no network), registered as a Flow Provider (`custom_openai`-style base URL) and a Flow Model. Anthropic with the developer key was not used: the trial needs no real answers, only real tool calls, permissions, usage rows and files.
- Life OS registered with Flow (`lifeos/ai/flow.py`, `hooks.py`): 18 tools under `flow_tools` as one-line wrappers of Ask's tools (`run_tool`), one agent "Life OS" under `flow_agents` (Ask's current instructions from the `ask` skill, the same tools, the site's first enabled model) and the skill `skills/ask/SKILL.md`. The agent only exists once a model is set up in Flow, so a site without one shows no agent; nothing breaks.
- Not offered to Flow: `suggest_actions` and `ask_one_question` (they draw Ask's own buttons and choices) and nothing sends or deletes, so no tool has `requires_confirmation`.

How to repeat the evidence below (inside `lifeos-bench`, with `python3 tools/fake_openai.py 8765` running):

```
echo "exec(open('/home/frappe/frappe-bench/apps/lifeos/tools/flow_trial.py').read(), globals()); run()" | bench --site lifeos.localhost console
```

Unit tests: `lifeos/tests/test_agents.py::TestFlow` (tools import with docstring and type hints; agent registered and lists the tools; the skill is Ask's skill; a second user is refused).

## 1. Can the Flow chat show inside Life OS's own screens?

**Partly: as Flow's own panel, not as a component of ours.**

- Frappe adds Flow's launcher script to every page under a route listed in `add_to_apps_screen`. Life OS is listed (`/life`), so `/life` already carries it: `curl /life` returns `flow_launcher.bundle.js` in the page (checked). It opens a slide-over panel with Flow's chat (Cmd/Ctrl+I) and exposes `window.flow.toggle()` and `window.flow.open({ session })`.
- The chat itself is a Vue "island" mounted by the launcher into a shadow-DOM panel (`flow/frontend/src/island.js`: `mount(el, context)`). It is not published as a component for other apps to import; no iframe is offered either (the launcher is `window.top` only, "not inside frames"). Flow's chat styling is Flow's, not ours (`frontend/COMPONENTS.md` is not applied to it).
- The island is built by `bench build` (it needs a network `yarn install` of Flow's own front end); the bench here had it unbuilt at first. On the server `bench update` builds it.

So the Ask drawer cannot become the Flow chat without taking Flow's panel as it is. The panel can be opened from our buttons (`window.flow.open`).

## 2. Spaces: a second user asks about the owner's records through Flow

**Refused, because the tools run as the asking user.**

Evidence (live Flow Server run, `tools/flow_trial.py`): the owner asks "What tasks do I have?" and the agent calls `lifeos__list_records`, which returns the owner's tasks. `stranger@lifeos.test`, with the Flow User role and no space, asks the same:

```
== stranger@lifeos.test: What tasks do I have?  status=Completed
tool_calls: lifeos__list_records {"kind": "tasks"}
output: From the tool: {"error": "Not allowed: you are not in any space."}
```

Unit test `test_4_a_second_user_cannot_read_or_change_the_owners_space_through_a_tool`: even when the tool is handed the owner's space, `list_records`, `search` and `make_task` as the family user return an error and create nothing. The wrappers build Ask's own `Context` for the asking user's default space, so Ask's space, Vault and scope checks are the ones in force. **A cost found on the way:** Flow only lets a user chat if they hold the role `Flow User`, and that role has desk access, so giving it to a Life User turns them from a Website User into a System User (the trial did this to the family user and Life OS's own test that Life Users have no desk access failed until the role was removed again). Flow through Life OS's own screens would call Flow's methods as the user too, so the same role is needed. This must be settled before the owner's family use Flow: either accept desk access for them, or run the engine for them as a service user. A weakness: Flow chooses the **default** space; a user in two spaces cannot say "the shared one" (Ask takes the space from the screen). Needs a `space` argument or the context described in section 7.

## 3. Cost: tokens, cost per chat, a monthly cap

- **Recorded:** yes. Every Flow Run keeps `usage` (input, output, cache read and write tokens, `cost`); the session transcript has a `usage` entry per model call. From the run above: `{"input_tokens": 480, "output_tokens": 120, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost": 0.0}`. The cost is `0.0` for a model the price table does not know (the fake one); for known models Flow computes it.
- **Cap:** none. Flow Settings has a small model, web search and guest rate limits (`guest_messages_per_hour`), no monthly limit.
- **Wrap with Life OS's own:** possible but not automatic. Flow does not write `Life AI Usage`, and the cap check (`lifeos.ai.client.check`) sits in front of Ask's own calls, not Flow's. To keep the cap we would need (a) a hook on Flow Run completion (`on_complete` in `FlowSession.chat`, or a doc event on Flow Run) that writes a `Life AI Usage` row from `usage`, and (b) a check before each turn, which Flow gives no hook for: only our own front end calling `frappe.flow.api.api.run` through a Life OS method that checks the cap first can enforce it. So the cap is only reliable when the chat goes through our own screen (section 10), not through `/flow` or the panel.

## 4. The owner's own key, other providers, a ChatGPT plan

- **Providers:** Anthropic, OpenAI, Gemini, OpenRouter, xAI, Groq, DeepSeek, Mistral, Cerebras, any OpenAI-compatible endpoint, a LiteLLM proxy. Ollama and others via a base URL.
- **Keys:** an API key per provider (Flow Provider) or per model (Flow Model), stored as Password fields; one set for the whole site, not per user. A model can be limited to roles.
- **The owner's own key:** yes, the key is entered by the owner in Flow. Not one key per user.
- **A ChatGPT plan** (a ChatGPT subscription login): **no.** Flow's "ChatGPT" entry means an OpenAI Platform API key (`platform.openai.com/api-keys`); there is no OAuth or plan sign-in in Flow (no `oauth` or `codex` in it). The same holds for a Claude plan.
- Life OS's own setting (#102) offers the same family of choices; Flow is wider (more providers, per-model keys), neither does plans.

## 5. What Ask does that Flow doesn't

| Ask has | In Flow | To keep it |
|---|---|---|
| **Threads by area** (`Life Ask Thread` with area, kept per person) | A Flow Session per chat, listed newest first with a title search; no area | Keep our thread list on top: a `Life Ask Thread` row holding the Flow Session name and area. Small. |
| **"Done" list with Undo** | Tool results are in the transcript; no Undo | Our tools already return `done_list` with an undo token (shown above for `make_task`). A Life OS screen over Flow's transcript can draw the list and call our undo method. In Flow's own UI the list is only text. |
| **Scope chips** (this area, this goal, everything) | None | Pass the scope as part of the message (section 7) and have the tools read it; or one agent per scope. Needs the tools to take a scope. |
| **Search-results fallback with no key** | A chat with no model shows its setup state | Keep: our screen runs `search` itself when `flow.agents()` is empty or the cap is reached. Plain code, nothing from Flow. |
| **Cost cap and `Life AI Usage`** | Section 3 | Our own front end plus an `on_complete` writer. |
| **`suggest_actions` buttons and `ask_one_question` choices** | Flow has its own question and approval cards (`needs_user`, `requires_confirmation`) | Port to Flow's tool form: possible, Flow's cards, not ours. |
| **Citations `[R3]` turned into links** | Plain text | Our own screen renders them (the agent keeps the same rules). |
| **Long mail reads in the background, shown by page** | The wrappers read a long period in one call (`Context.background`); Flow has `background` tools of its own | Not tried at length with a real model. The per-page progress line would be ours. |

## 6. Recommendation

**Later, and in a particular way: Flow as the engine, our screens on top. Do not send the owner to `/flow`.**

Why not now: the owner's wishes (a panel that knows the current record, files dropped anywhere, the mic, a phone bar replacing + Capture) all need our own UI; Flow's own panel cannot take context, cannot keep the Vault safe (section 8) and has no cap (section 3). Why not never: Flow gives, for free, the loop, sessions, streaming events, providers, per-model keys, approval cards, memory, skills and file extraction, which we would otherwise keep writing.

If switched (the follow-up issue):

- **Deleted:** the model loop and the Anthropic backend callers of Ask in `lifeos/ai/client.py` (`call`, `AnthropicBackend`, `backend`, the retry and error code that only Ask used; the Brain still calls `client.call` until it moves to Flow triggers, so the module stays for now), `lifeos/ai/ask.py`, `lifeos/ai/ask_job.py`, `lifeos/ai/fake.py`'s Ask parts, the `Life Ask Message` DocType and the message part of `Life Ask Thread`, the provider setting from #102 (Flow Provider replaces it) and their tests and acceptance checks.
- **Stays:** `lifeos/ai/tools.py` (the tools, with Ask's space, Vault and scope checks, through `lifeos/ai/flow.py`), `Life Ask Thread` as a thin list (name, area, Flow Session), `Life AI Usage` and its cap, the Done list and Undo, the search fallback, the skills, the Ask screens.
- **Added:** a Life OS method that creates a Flow Session, applies the cap, adds the context and calls `run`; a usage writer on run completion; scope and space arguments in the wrappers.

## 7. A panel everywhere, with the current record

- **Flow's own panel:** `window.flow.open({ session })` only; it takes no context. It is Flow's chat in Flow's style (section 1).
- **Our own panel on Flow's engine:** yes, and the current record travels as text. The run API takes a message; the trial sent `[About: Task 'Renew club membership'] What tasks do I have?` and it reached the model as the user message (transcript entry `user_message`, shown in section 10). `FlowSession.chat()` in Python also takes `reference_doctype` and `reference_name`, but the whitelisted `run` does not expose them, so a Life OS method would call `chat()` itself, which also lets it check the cap first.
- A panel kept open across Life OS screens is ours to build (Vue state in the shell); Flow does not have to know.

## 8. Files, and the Vault

- **Can a user attach files?** Yes: upload a File, `attach_file` validates and extracts text, `run(..., attachments=[file])` sends it.
- **Do they reach our tools as File records?** The File is saved (private) and named in the message as `<file name="kyc.txt" file="0cdd7d2cb2" url="/private/files/kyc.txt" size="1 KB">`. A tool is told the File name, so it could file it: yes.
- **Without the model seeing a Vault file's text?** **No.** Flow always extracts the text (OCR for images, for text-only models) and puts it in the turn: in full up to 32,000 characters, otherwise a preview of 1,000 characters plus a `read_attachment` tool. The trial's message shows the file's text inside the user message (`owner note: KYC test file`). The only way to keep a Vault file out of the model is not to attach it through Flow: our own screen takes the drop, files it to the Vault (reading it locally, #104), and sends the model only a line such as "Saved Aadhaar.pdf to the Vault". That works when the chat is ours (section 10) and not with Flow's own chat.

## 9. Voice

Flow's chat has no microphone. The run API takes text, so Life OS's own speech-to-text (faster-whisper, #104) can fill the message box and send the result like any typed message: **yes**, with our own chat screen. Nothing to build in Flow.

## 10. Our own chat UI on Flow's engine

**Works.** The whole turn goes through Flow's whitelisted methods, with the cookie of the signed-in user, and our Vue front end would call the same ones (HTTP, run on the live bench as the owner, `curl` with a session cookie):

```
POST frappe.flow.api.api.create_session   agent=lifeos/Life OS     -> {"name": "8sj0bp7bch", "agent": "lifeos/Life OS", "model": "Fake model", ...}
POST upload_file                          file=kyc.txt, is_private  -> File 0cdd7d2cb2
POST frappe.flow.api.api.attach_file      file=0cdd7d2cb2           -> {"file": "0cdd7d2cb2", "file_name": "kyc.txt", "file_size": 26}
POST frappe.flow.api.api.run              session, message="[About: Task 'Renew club membership'] What tasks do I have?", attachments=["0cdd7d2cb2"]
                                                                    -> {"run": "8vjic4f19c", "status": "started"}
GET  frappe.flow.api.api.entries?session=8sj0bp7bch                 -> the transcript:
  user_message      "[About: Task 'Renew club membership'] What tasks do I have?\n<file name="kyc.txt" file="0cdd7d2cb2" url="/private/files/kyc.txt" ...>owner note: KYC test file</file>"
  assistant_message tool_call lifeos__list_records {"kind": "tasks"}
  usage             input_tokens 120, output_tokens 30, cost 0.0
  tool_result       {"total": 9, "rows": [{"ref": "R1", "title": "Agree audit scope with the auditor", ...}]}
  assistant_message (the answer)
```

The same calls give: the stream (poll `entries?since=<seq>`, or Flow's realtime events), history (`list_sessions`), stop (`abort`), approval answers (`resume`), model change (`set_model`). Permissions and spaces apply because the tool runs as the user (section 2). A third path, a Python method in Life OS that calls `FlowSession.chat()`, is better for production: it takes `reference_doctype` and `reference_name`, and checks the cap before the turn.

Not shown: the real browser panel of Flow (`/flow`, the launcher), because Flow's front-end island needs Flow's own `yarn install` at build time, which the local bench could not finish; the evidence above is the live server and API, not screenshots.

## Fixes the upgrade needed

None to Life OS's own code: the unit suite passes on 16.61.0 unchanged. The CI bench builds and the Docker bench were already on 16.61.0 when this round began; README and CI name it.

## Decision for the owner

1. Keep Ask as is for now.
2. Open a follow-up: "Ask on Flow's engine": our own chat screen (panel everywhere with the current record, drop zone to the Vault, mic, phone bar) calling a Life OS method that applies the cap and starts a Flow Session with the "Life OS" agent. Close the gaps in section 5 there.
3. Do not make `/flow` the way the owner reaches Life OS; use it only to try the agent.
