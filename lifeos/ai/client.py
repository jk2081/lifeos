"""The one place Life OS calls an AI model (UX fixes, set 5). Ask and the AI insights go through `call`.

- Provider: the Anthropic API through the official `anthropic` package (pinned in pyproject.toml).
- Key: Life Settings.anthropic_api_key (a Password field, encrypted by Frappe), or `anthropic_api_key` in site config.
  It is never logged, put in an error message or sent to the browser.
- Spend cap: Life Settings.monthly_cap_usd, and an optional cap per feature (Life Settings.feature_caps). A call is refused
  (CapReached, an AIError the caller turns into its fallback) once either is reached. Every call's feature, model, tokens
  (cached ones priced as cached), cost, record and user are written to Life AI Usage.
- Tests and the acceptance site never call the real API: `frappe.flags.lifeos_ai_backend` (set by tests) or the site
  config `lifeos_fake_ai` (the acceptance site) selects the fake in fake.py, which records what it was sent.
"""
import frappe
from frappe import _
from frappe.utils import flt, now_datetime

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


class AIError(frappe.ValidationError):
	pass


class NotSetUp(AIError):
	pass


class CapReached(AIError):
	pass


def month(dt=None):
	return (dt or now_datetime()).strftime("%Y-%m")


def api_key():
	"""The key, or None. Read only here and only on the server."""
	from frappe.utils.password import get_decrypted_password

	key = None
	try:
		key = get_decrypted_password("Life Settings", "Life Settings", "anthropic_api_key", raise_exception=False)
	except Exception:
		key = None
	return key or frappe.conf.get("anthropic_api_key") or None


def is_set_up():
	return bool(api_key())


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


def prices():
	return {m: (i, o) for m, (i, o, _c) in price_table().items()}


def cost_of(model, input_tokens, output_tokens, cached_tokens=0, cache_write_tokens=0):
	"""Dollars for one call. `input_tokens` are the ones read at the full price; cached reads are priced as cached and cache
	writes at 1.25 times the input price."""
	inp, out, cached = price_table().get(model, (0.0, 0.0, 0.0))
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
	if feature:
		return flt(frappe.db.sql("select sum(cost) from `tabLife AI Usage` where month=%s and purpose=%s", (m or month(), feature))[0][0])
	return flt(frappe.db.sql("select sum(cost) from `tabLife AI Usage` where month=%s", m or month())[0][0])


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
		"cost": cost, "purpose": purpose, "space": space, "reference_doctype": ref[0], "reference_name": ref[1]}).insert(ignore_permissions=True)
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
	return AnthropicBackend(key)


class AnthropicBackend:
	"""Streams one request with the official SDK and returns the final message as plain dicts."""

	def __init__(self, key):
		import anthropic

		self.client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT, max_retries=RETRIES)

	def run(self, params, on_text=None):
		import anthropic

		extra = {}
		if params["model"] in FALLBACK_MODELS:
			extra = {"extra_headers": {"anthropic-beta": FALLBACK_BETA}, "extra_body": {"fallbacks": "default"}}
		try:
			with self.client.messages.stream(**params, **extra) as stream:
				for event in stream:
					if on_text and event.type == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
						on_text(event.delta.text)
				final = stream.get_final_message()
		except anthropic.RateLimitError:
			raise AIError(_("The AI service is busy. Try again in a minute."))
		except anthropic.APIConnectionError:
			raise AIError(_("Could not reach the AI service."))
		except anthropic.AuthenticationError:
			raise AIError(_("The AI service refused the API key. Check it in Settings, Assistant, Ask and AI."))
		except anthropic.APIStatusError as e:
			raise AIError(_("The AI service answered with an error ({0}).").format(e.status_code))
		u = final.usage
		return {"content": [b.to_dict() for b in final.content], "stop_reason": final.stop_reason, "model": final.model,
			"usage": {"input_tokens": int(u.input_tokens or 0), "output_tokens": int(u.output_tokens or 0),
				"cached_tokens": int(getattr(u, "cache_read_input_tokens", 0) or 0),
				"cache_write_tokens": int(getattr(u, "cache_creation_input_tokens", 0) or 0)}}


def call(purpose, system, messages, tools=None, kind="ask", max_tokens=8000, on_text=None, space=None, effort=None, schema=None, user=None, reference=None):
	"""One request to the model, after the cap check, with its usage recorded. Returns
	{content: [blocks as dicts], stop_reason, usage, cost, model}. `kind` picks the Ask model or the short-task model.
	`purpose` is the feature the cost is booked to; `reference` is (doctype, name) of the record the call was for. Over a cap it
	raises CapReached (an AIError): callers catch AIError and fall back."""
	check(purpose)
	model = models()["short" if kind == "short" else "ask"]
	params = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages,
		"output_config": {"effort": effort or ("low" if kind == "short" else "medium")}}
	if tools:
		params["tools"] = tools
	if schema:  # structured output: the answer is JSON that matches the schema
		params["output_config"]["format"] = {"type": "json_schema", "schema": schema}
	out = backend().run(params, on_text)
	out["cost"] = record(out.get("model") or model, out["usage"], purpose, space, user, reference)
	out["model"] = out.get("model") or model
	return out


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
