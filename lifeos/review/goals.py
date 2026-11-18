"""Tab 3, Goals (set 8). Filled in by step 5; until then the tab is never done."""


class GoalPlan:
	def __init__(self, review):
		self.review = review

	def ready(self):
		return {"ok": False, "left": ["Goals arrive with step 5."]}
