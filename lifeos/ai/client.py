"""The one place Life OS calls an AI model (UX fixes, set 5). Ask and the AI insights go through `call`.

- Provider: the Anthropic API through the official `anthropic` package (pinned in pyproject.toml), or (issue 102) another
  Anthropic-compatible service at Life Settings.ai_base_url, which gets the request without Anthropic's extras.
- Key: Life Settings.anthropic_api_key, or ai_other_key for another service (Password fields, encrypted by Frappe), or
  `anthropic_api_key` in site config.
  It is never logged, put in an error message or sent to the browser.
- Spend cap: Life Settings.monthly_cap_usd, and an optional cap per feature (Life Settings.feature_caps). A call is refused
  (CapReached, an AIError the caller turns into its fallback) once either is reached. Every call's feature, model, tokens
  (cached ones priced as cached), cost, record and user are written to Life AI Usage.
- Tests and the acceptance site never call the real API: `frappe.flags.lifeos_ai_backend` (set by tests) or the site
  config `lifeos_fake_ai` (the acceptance site) selects the fake in fake.py, which records what it was sent.
"""
import re

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_to_date, flt, now_datetime, today

# US dollars per million tokens, input and output. Editable in Settings > Admin > AI.
DEFAULT_PRICES = {
	"claude-sonnet-5-5": (2.0, 10.0),
	"claude-haiku-5-5": (0.10, 0.50),
	"claude-opus-5-5": (4.0, 20.0),
}
DEFAULT_ASK_MODEL = "claude-sonnet-5-5"
DEFAULT_SHORT_MODEL = "claude-haiku-5-5"
TIMEOUT = 60  # seconds per request; the SDK retries 408, 409, 429 and 5xx itself
RETRIES = 3
# server-side fallback on a refusal, for the models that take it (the Haiku line has none)
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5")


ANTHROPIC = "Anthropic"
OTHER = "Another service (Anthropic-compatible)"
OFF_KEY = "lifeos_ai_off"  # the reason the AI service is not answering, until a call succeeds again (a global default)
REASON_LENGTH = 240


class AIError(frappe.ValidationError):
	"""`unavailable` is set when the cause is credit, the key or the provider, so the Brain is shown as off."""

	unavailable = False
	reason = ""


class NotSetUp(AIError):
	pass


class CapReached(AIError):
	pass


class ToolsRefused(AIError):
	"""The provider does not take tools; Ask answers from search results only."""


def month(dt=None):
	return (dt or now_datetime()).strftime("%Y-%m")


def is_other():
	"""True when Life Settings points at another Anthropic-compatible service (issue 102)."""
	return frappe.get_cached_doc("Life Settings").get("ai_provider") == OTHER


def base_url():
	"""The other service's address, or None for Anthropic itself."""
	return ((frappe.get_cached_doc("Life Settings").get("ai_base_url") or "").strip() or None) if is_other() else None


def api_key():
	"""The key of the chosen provider, or None. Read only here and only on the server."""
	from frappe.utils.password import get_decrypted_password

	other = is_other()
	key = None
	try:
		key = get_decrypted_password("Life Settings", "Life Settings", "ai_other_key" if other else "anthropic_api_key", raise_exception=False)
	except Exception:
		key = None
	return key or (None if other else frappe.conf.get("anthropic_api_key")) or None


def is_set_up():
	return bool(api_key()) and (not is_other() or bool(base_url()))


def models():
	s = frappe.get_cached_doc("Life Settings")
	return {"ask": s.get("ask_model") or DEFAULT_ASK_MODEL, "short": s.get("short_model") or DEFAULT_SHORT_MODEL}


def price_table():
	"""{model: (input, output, cached input)} in dollars per million tokens. A blank cached price is a tenth of the input price."""
	out = {m: (i, o, i / 10) for m, (i, o) in DEFAULT_PRICES.items()}
	for r in frappe.get_cached_doc("Life Settings").get("ai_prices") or []:
		if r.model:
			cached = flt(r.get("cached_per_mtok")) or flt(r.input_per_mtok) / 10
			out[r.model] = (flt(r.input_per_mtok), flt(r.output_per_mtok), cached)
	return out


def dearest():
	"""A model with no price is counted at the most expensive known price, so the cap still holds, until the owner adds one."""
	table = price_table().values()
	return tuple(max(p[i] for p in table) for i in range(3))


def unpriced():
	"""The models in use (Ask, quick jobs) that have no price row."""
	table = price_table()
	return [m for m in dict.fromkeys(models().values()) if m not in table]


def prices():
	return {m: (i, o) for m, (i, o, _c) in price_table().items()}


def cost_of(model, input_tokens, output_tokens, cached_tokens=0, cache_write_tokens=0):
	"""Dollars for one call. `input_tokens` are the ones read at the full price; cached reads are priced as cached and cache
	writes at 1.25 times the input price."""
	inp, out, cached = price_table().get(model) or dearest()
	total = (int(input_tokens or 0) * inp + int(cache_write_tokens or 0) * inp * 1.25 + int(cached_tokens or 0) * cached
		+ int(output_tokens or 0) * out)
	return round(total / 1_000_000, 6)


def cap():
	return flt(frappe.get_cached_doc("Life Settings").get("monthly_cap_usd")) or 30.0


def feature_caps():
	"""{feature: dollars a month}; a feature that is not listed has no cap of its own."""
	import json

	try:
		raw = json.loads(frappe.get_cached_doc("Life Settings").get("feature_caps") or "{}")
	except ValueError:
		return {}
	return {str(k): flt(v) for k, v in raw.items() if isinstance(raw, dict) and flt(v) > 0}


def spent(m=None, feature=None):
	usage = frappe.qb.DocType("Life AI Usage")
	query = frappe.qb.from_(usage).select(Sum(usage.cost)).where(usage.month == (m or month()))
	if feature:
		query = query.where(usage.purpose == feature)
	return flt(query.run()[0][0])


def spend_status():
	"""This month's spend against the cap, for the Ask page and Settings: "This month: $4.20 of $30"."""
	s, c = spent(), cap()
	return {"month": month(), "spent": round(s, 2), "cap": c, "reached": s >= c, "set_up": is_set_up(),
		"text": f"This month: ${s:,.2f} of ${c:,.0f}"}


def check(purpose="Ask"):
	"""Stop before a call: no key, the month's spend has reached the cap, or this feature has reached its own cap."""
	if not is_set_up():
		raise NotSetUp(_("Ask is not set up yet."))
	st = spend_status()
	if st["reached"]:
		raise CapReached(_("This month's AI spend has reached the cap: ${0} of ${1}.").format(f"{st['spent']:,.2f}", f"{st['cap']:,.0f}"))
	own = feature_caps().get(purpose)
	if own and spent(feature=purpose) >= own:
		raise CapReached(_("{0} has reached its own cap for this month: ${1} of ${2}.").format(purpose, f"{spent(feature=purpose):,.2f}", f"{own:,.0f}"))
	return st


def record(model, usage, purpose, space=None, user=None, reference=None):
	"""Write one call to Life AI Usage. `usage` has input_tokens, output_tokens and optionally cached_tokens and cache_write_tokens."""
	cost = cost_of(model, usage.get("input_tokens"), usage.get("output_tokens"), usage.get("cached_tokens"), usage.get("cache_write_tokens"))
	ref = reference or (None, None)
	frappe.get_doc({"doctype": "Life AI Usage", "user": user or frappe.session.user, "month": month(), "model": model,
		"input_tokens": int(usage.get("input_tokens") or 0), "output_tokens": int(usage.get("output_tokens") or 0),
		"cached_tokens": int(usage.get("cached_tokens") or 0), "cache_write_tokens": int(usage.get("cache_write_tokens") or 0),
		"cost": cost, "purpose": purpose, "space": space, "reference_doctype": ref[0], "reference_name": ref[1]}).insert(ignore_permissions=True)  # system: the cost log is written for whoever made the call, who may not write Life AI Cost
	return cost


def backend():
	"""The object that talks to the model: the fake for tests and the acceptance site, else the Anthropic SDK."""
	if frappe.flags.lifeos_ai_backend:
		return frappe.flags.lifeos_ai_backend
	key = api_key()
	# the acceptance site: the flag is read from the site config file itself (a long-running server keeps an old copy of
	# frappe.conf), and a key that starts with "fake-" is never sent anywhere
	if frappe.get_site_config().get("lifeos_fake_ai") or str(key).startswith("fake-"):
		from lifeos.ai import fake

		return fake.SiteFake()
	return AnthropicBackend(key, base_url())


def clean(text, extra=()):
	"""A provider's message for people: one line, no key or address in it, shortened."""
	text = " ".join(str(text or "").split())
	for secret in [api_key(), base_url(), *extra]:
		if secret and len(str(secret)) > 4:
			text = text.replace(str(secret), "…")
	text = re.sub(r"\b(sk|key)-[\w-]{8,}", "…", text)
	text = re.sub(r"https?://\S+", "", text).strip()
	return text if len(text) <= REASON_LENGTH else text[: REASON_LENGTH - 1].rstrip() + "…"


def error_from(status, message):
	"""The AIError for a provider's answer: what the provider said, shortened and cleaned, and whether the Brain is off because of it."""
	message = clean(message)
	other = is_other()
	credit = status == 402 or bool(re.search(r"credit|balance|billing|quota|insufficient", message, re.I))
	if status == 429 and not credit:
		e = AIError(_("The AI service is busy. Try again in a minute."))
		e.reason = message
		return e
	if status in (401, 403):
		text = _("The AI service refused the API key. Check it in Settings, Advanced, AI key and cost.")
		text = f"{text} {message}" if other and message else text
		unavailable = True
	elif credit:
		text = message if other and message else _("Your AI credit has run out. Top up at console.anthropic.com, or check the linked organisation.")
		unavailable = True
	elif status and status >= 500:
		text = message or _("The AI service answered with an error ({0}).").format(status)
		unavailable = True
	elif status == 400 and message and re.search(r"\btools?\b", message, re.I):
		e = ToolsRefused(message)
		e.reason = message
		return e
	else:
		text = message or _("The AI service answered with an error ({0}).").format(status)
		unavailable = False
	e = AIError(text)
	e.unavailable, e.reason = unavailable, message or text
	return e


def note_unavailable(e):
	"""The Brain is off: remember why until a call works again, and write one Life Action Log row an hour."""
	reason = clean(str(e))
	frappe.db.set_default(OFF_KEY, reason)
	log = frappe.qb.DocType("Life Action Log")
	recent = frappe.qb.from_(log).select(log.name).where((log.kind == "AI unavailable") & (log.creation > add_to_date(now_datetime(), hours=-1))).limit(1).run()  # system: one row an hour, whoever asks
	space = frappe.db.get_single_value("Life Settings", "default_space") or frappe.db.get_value("Life Space", {}, "name")
	if recent or not space:
		return
	frappe.get_doc({"doctype": "Life Action Log", "kind": "AI unavailable", "space": space, "date": today(), "reason": reason}).insert(ignore_permissions=True)  # system: written for whoever made the failing call


def brain_off():
	"""Why the Brain is off ("Your AI credit has run out…"), or None when the last call worked."""
	return frappe.db.get_default(OFF_KEY) or None


def mark_working():
	if frappe.db.get_default(OFF_KEY):
		frappe.defaults.clear_default(OFF_KEY, parent="__default")


class AnthropicBackend:
	"""Streams one request with the official SDK and returns the final message as plain dicts. Another Anthropic-compatible
	service gets the same request without the extras only Anthropic takes (the fallback beta)."""

	def __init__(self, key, url=None):
		import anthropic

		self.other = bool(url)
		self.client = anthropic.Anthropic(api_key=key, base_url=url, timeout=TIMEOUT, max_retries=RETRIES) if url else anthropic.Anthropic(api_key=key, timeout=TIMEOUT, max_retries=RETRIES)

	def run(self, params, on_text=None):
		import anthropic

		extra = {}
		if not self.other and params["model"] in FALLBACK_MODELS:
			extra = {"extra_headers": {"anthropic-beta": FALLBACK_BETA}, "extra_body": {"fallbacks": "default"}}
		try:
			with self.client.messages.stream(**params, **extra) as stream:
				for event in stream:
					if on_text and event.type == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
						on_text(event.delta.text)
				final = stream.get_final_message()
		except anthropic.APIConnectionError:
			raise AIError(_("Could not reach the AI service."))
		except anthropic.APIStatusError as e:
			raise error_from(e.status_code, _provider_message(e))
		u = final.usage
		return {"content": [b.to_dict() for b in final.content], "stop_reason": final.stop_reason, "model": final.model,
			"usage": {"input_tokens": int(u.input_tokens or 0), "output_tokens": int(u.output_tokens or 0),
				"cached_tokens": int(getattr(u, "cache_read_input_tokens", 0) or 0),
				"cache_write_tokens": int(getattr(u, "cache_creation_input_tokens", 0) or 0)}}


def _provider_message(e):
	"""The provider's own `error.message` from an API error."""
	body = getattr(e, "body", None)
	err = body.get("error") if isinstance(body, dict) else None
	if isinstance(err, dict) and err.get("message"):
		return err["message"]
	if isinstance(body, dict) and isinstance(body.get("message"), str):
		return body["message"]
	return getattr(e, "message", "") or ""


def without_cache_control(x):
	"""A copy of the request without any cache_control, which only Anthropic takes."""
	if isinstance(x, dict):
		return {k: without_cache_control(v) for k, v in x.items() if k != "cache_control"}
	if isinstance(x, list):
		return [without_cache_control(v) for v in x]
	return x


def schema_instruction(schema):
	import json

	return "Answer with JSON only, matching this schema: " + json.dumps(schema)


def call(purpose, system, messages, tools=None, kind="ask", max_tokens=8000, on_text=None, space=None, effort=None, schema=None, user=None, reference=None):
	"""One request to the model, after the cap check, with its usage recorded. Returns
	{content: [blocks as dicts], stop_reason, usage, cost, model}. `kind` picks the Ask model or the short-task model.
	`purpose` is the feature the cost is booked to; `reference` is (doctype, name) of the record the call was for. Over a cap it
	raises CapReached (an AIError): callers catch AIError and fall back. Another service gets no effort, no structured-output
	format and no cache_control: a schema goes into the system text and the answer is parsed, with one retry."""
	check(purpose)
	model = models()["short" if kind == "short" else "ask"]
	other = is_other()
	params = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
	if other:
		if schema:
			params["system"] = f"{system}\n\n{schema_instruction(schema)}"
		params = without_cache_control(params)
	else:
		params["output_config"] = {"effort": effort or ("low" if kind == "short" else "medium")}
		if schema:  # structured output: the answer is JSON that matches the schema
			params["output_config"]["format"] = {"type": "json_schema", "schema": schema}
	if tools:
		params["tools"] = tools
	out = _run(params, on_text)
	if other and schema and json_of(out["content"]) is None:  # one retry when the answer is not JSON
		first = out
		out = _run(params, on_text)
		out["usage"] = {k: int(first["usage"].get(k) or 0) + int(out["usage"].get(k) or 0) for k in set(first["usage"]) | set(out["usage"])}
	out["cost"] = record(out.get("model") or model, out["usage"], purpose, space, user, reference)
	out["model"] = out.get("model") or model
	return out


def _run(params, on_text):
	try:
		out = backend().run(params, on_text)
	except AIError as e:
		if e.unavailable:
			note_unavailable(e)
		raise
	mark_working()
	return out


def test_connection():
	"""One tiny call with the current setting: {ok, model, text}. The provider's own reason when it fails; no spend cap check, a
	call of about five tokens."""
	if not is_set_up():
		return {"ok": False, "text": _("Add the key first.") if not is_other() or base_url() else _("Add the service's address and key first.")}
	model = models()["ask"]
	params = {"model": model, "max_tokens": 5, "system": "Reply with one word.", "messages": [{"role": "user", "content": "Say ok"}]}
	if not is_other():
		params["output_config"] = {"effort": "low"}
	try:
		out = _run(params, None)
	except AIError as e:
		return {"ok": False, "text": str(e)}
	record(out.get("model") or model, out["usage"], "Test connection")
	return {"ok": True, "model": model, "text": _("Working: {0} answered").format(out.get("model") or model)}


def text_of(content):
	return "".join(b.get("text", "") for b in content if b.get("type") == "text")


def json_of(content):
	"""The JSON object of a structured answer, or None."""
	import json
	import re

	text = text_of(content).strip()
	if text.startswith("```"):
		text = re.sub(r"^```\w*\n?|```$", "", text).strip()
	try:
		return json.loads(text)
	except ValueError:
		m = re.search(r"\{.*\}", text, re.S)
		try:
			return json.loads(m.group(0)) if m else None
		except ValueError:
			return None
