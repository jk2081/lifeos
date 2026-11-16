"""The AI insight detector (UX fixes, set 5). Filled in at step 8; until then it finds nothing."""


def candidates(space, user):
	from lifeos.ai import client

	if not client.is_set_up():
		return [], "AI insights skipped: no API key."
	return [], None
