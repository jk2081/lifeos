"""Citations in an Ask answer: [R3] markers become numbered [1] in order of first use."""
import re

MARK = re.compile(r"\[(R\d+(?:\s*,\s*R\d+)*)\]")


def cite(text, ctx):
	"""Turn [R3] markers into numbered markers [1] in order of first use, and list the cited records."""
	order = []

	def sub(m):
		nums = []
		for r in re.split(r"\s*,\s*", m.group(1)):
			if r not in ctx.refs:
				continue
			if r not in order:
				order.append(r)
			nums.append(str(order.index(r) + 1))
		return "".join(f"[{n}]" for n in nums)

	text = MARK.sub(sub, text or "")
	cited = []
	for i, r in enumerate(order, 1):
		x = ctx.refs[r]
		cited.append({"n": i, "doctype": x["doctype"], "name": x["name"], "title": x["title"], "kind": x["kind"], "date": x["date"], "pane": x["pane"], "route": x.get("route")})
	return text, cited

