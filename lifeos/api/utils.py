"""Small helpers shared by the API modules."""
import frappe
from frappe.query_builder import Case, Order
from frappe.query_builder import functions as fn
from frappe.utils import cint
from pypika.terms import Tuple

MAX_PAGE = 100


def page(start=0, page_length=20):
	"""Clamp paging arguments. No list method returns more than 100 rows."""
	return max(cint(start), 0), min(max(cint(page_length) or 20, 1), MAX_PAGE)


def parse(value, default=None):
	"""Arguments arrive as JSON strings over HTTP and as objects over MCP."""
	if value is None or value == "":
		return default
	if isinstance(value, str):
		try:
			return frappe.parse_json(value)
		except ValueError:
			return value
	return value


def flag(value) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


def names_map(doctype, names, field):
	names = [n for n in set(names) if n]
	if not names:
		return {}
	return dict(frappe.get_list(doctype, filters={"name": ("in", names)}, fields=["name", field], as_list=True))


def user_names(users):
	users = [u for u in set(users) if u]
	if not users:
		return {}
	out = {}
	for name, first, full in frappe.get_all("User", filters={"name": ("in", users)}, fields=["name", "first_name", "full_name"], as_list=True):  # system: user names, not a space record
		out[name] = first or full or name
	return out


def descendants(space, area):
	"""The area and every area below it."""
	rows = frappe.get_list("Life Area", filters={"space": space}, fields=["name", "parent_area"], limit=2000)
	children = {}
	for r in rows:
		children.setdefault(r.parent_area, []).append(r.name)
	out, stack = [], [area]
	while stack:
		cur = stack.pop()
		if cur in out:
			continue
		out.append(cur)
		stack.extend(children.get(cur, []))
	return out


def area_filter(space, area, column, values, also_in=None):
	"""LEGACY (SQL text; the new API is area_criterion). SQL for an Area filter, the same on every list and under the lens (UX fixes, set 6): the area with its sub-areas,
	or "none" for records with no area. A record listing the area (or a sub-area) in "also in" counts as in it.
	`also_in` is the parenttype of a record that can also be filed under other areas, or "index" for Life Index rows,
	whose record is named by ref_doctype and ref_name."""
	if area == "none":
		return f"ifnull({column}, '') = ''"
	values["area_ids"] = descendants(space, area)
	sql = f"{column} in %(area_ids)s"
	alias = column.rsplit(".", 1)[0] + "." if "." in column else ""
	if also_in == "index":
		from lifeos.library.index import also_in_sql

		sql = f"({sql} or {also_in_sql('area_ids', alias)})"
	elif also_in:
		if also_in not in ALSO_IN:
			frappe.throw(frappe._("Unknown filed DocType {0}.").format(also_in), title=frappe._("Unknown filed DocType"))
		sql = (f"({sql} or exists (select 1 from `tabLife Also In` ai where ai.parent = {alias}name "
			f"and ai.parenttype = '{also_in}' and ai.area in %(area_ids)s))")
	return sql


def area_criterion(space, area, table, also_in=None):
	"""The Area filter as a pypika criterion over `table` (new API; area_filter is the SQL-text legacy of it). The area with its
	sub-areas, or "none" for records with no area. A record listing the area (or a sub-area) in "also in" counts as in it.
	`also_in` is the parenttype of a record that can also be filed under other areas, or "index" for Life Index rows,
	whose record is named by ref_doctype and ref_name."""
	if area == "none":
		return fn.IfNull(table.area, "") == ""
	ids = descendants(space, area)
	crit = table.area.isin(ids)
	if also_in == "index":
		crit = crit | Tuple(table.ref_doctype, table.ref_name).isin(_also_in_rows(ids))
	elif also_in:
		if also_in not in ALSO_IN:
			frappe.throw(frappe._("Unknown filed DocType {0}.").format(also_in), title=frappe._("Unknown filed DocType"))
		crit = crit | table.name.isin(_also_in_rows(ids, also_in))
	return crit


def _also_in_rows(area_ids, parenttype=None):
	"""The Life Also In rows filed under any of the areas: (parenttype, parent) pairs, or just the parent of one parenttype."""
	ai = frappe.qb.DocType("Life Also In")
	if parenttype:
		return frappe.qb.from_(ai).select(ai.parent).where((ai.parenttype == parenttype) & ai.area.isin(area_ids))
	return frappe.qb.from_(ai).select(ai.parenttype, ai.parent).where(ai.area.isin(area_ids))


# the DocTypes with an "also in" table
ALSO_IN = ("Life Task", "Life Note", "Life Inbox Item", "Life Chat Log", "Life Vault Document")


def lens_area(area):
	"""The lens's area as a list argument: None for "All of life"."""
	area = str(area or "").strip()
	return None if area in ("", "all") else area


def order_by(sort, direction, allowed, default):
	"""LEGACY (SQL text; the new API is sort_terms). An ORDER BY for a list. `allowed` maps the sort keys a caller may name to SQL, so nothing else reaches the query."""
	if not sort or sort not in allowed:
		return default
	way = "desc" if str(direction or "").lower() == "desc" else "asc"
	return ", ".join(f"{part.strip()} {way}" for part in allowed[sort].split(","))


# ---- standard Frappe filters and order_by on the list methods ----
# The list screens send what the library's Filter and SortBy controls produce: a list of [fieldname, operator, value]
# and an order_by string. Every field name is checked against the DocType's meta before it reaches SQL, and every
# value is passed as a query parameter.

STANDARD_COLUMNS = ("name", "owner", "creation", "modified", "modified_by")
OPERATORS = {"=": "=", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">=", "like": "like", "not like": "not like",
	"in": "in", "not in": "not in", "is": "is", "between": "between", "timespan": "timespan"}
NO_COLUMN = ("Section Break", "Column Break", "Tab Break", "HTML", "Table", "Table MultiSelect", "Button", "Image", "Fold", "Heading")
MAX_FILTERS = 25


def column(doctype, fieldname, alias=""):
	"""The SQL for one column of a DocType, or an error if the DocType has no such column."""
	fieldname = str(fieldname or "").strip()
	meta = frappe.get_meta(doctype)
	field = meta.get_field(fieldname)
	if fieldname not in STANDARD_COLUMNS and (not field or field.fieldtype in NO_COLUMN):
		frappe.throw(frappe._("{0} has no field {1}.").format(doctype, frappe.bold(fieldname)), frappe.ValidationError, title=frappe._("Field does not exist"))
	return f"{alias}.`{fieldname}`" if alias else f"`{fieldname}`"


def _fieldtype(doctype, fieldname):
	if fieldname in ("creation", "modified"):
		return "Datetime"
	field = frappe.get_meta(doctype).get_field(fieldname)
	return field.fieldtype if field else "Data"


def _parsed_filters(doctype, filters):
	"""The checked and normalised conditions of a standard filter list, as (index, fieldname, op, value, fieldtype).
	Raises on an unknown field, operator or shape; a list filter with no items is dropped."""
	filters = parse(filters, [])
	if not filters:
		return
	if isinstance(filters, dict):
		filters = [[k, "=", v] if not isinstance(v, (list, tuple)) else [k, v[0], v[1]] for k, v in filters.items()]
	if not isinstance(filters, (list, tuple)) or len(filters) > MAX_FILTERS:
		frappe.throw(frappe._("filters must be a list of at most {0} conditions.").format(MAX_FILTERS), frappe.ValidationError, title=frappe._("Too many filters"))
	for i, f in enumerate(filters):
		if not isinstance(f, (list, tuple)) or len(f) not in (3, 4):
			frappe.throw(frappe._("Each filter is [fieldname, operator, value]."), frappe.ValidationError, title=frappe._("Filter shape is wrong"))
		if len(f) == 4:
			if f[0] != doctype:
				frappe.throw(frappe._("Filters on {0} are not supported here.").format(frappe.bold(str(f[0]))), frappe.ValidationError, title=frappe._("Filter field not supported"))
			f = f[1:]
		fieldname, op, value = f
		op = OPERATORS.get(str(op or "").strip().lower())
		if not op:
			frappe.throw(frappe._("Unknown filter operator {0}.").format(frappe.bold(str(f[1]))), frappe.ValidationError, title=frappe._("Unknown filter operator"))
		column(doctype, fieldname)  # the field must exist
		ftype = _fieldtype(doctype, fieldname)
		if ftype == "Check" and isinstance(value, str):
			value = 1 if value.strip().lower() in ("yes", "1", "true") else 0
		if op in ("in", "not in"):
			value = value if isinstance(value, (list, tuple)) else [v.strip() for v in str(value or "").split(",") if v.strip()]
			if not value:
				continue
			value = [str(v) for v in value][:200]
		elif op in ("between", "timespan"):
			if op == "timespan":
				from frappe.utils.data import get_timespan_date_range
				try:
					value = get_timespan_date_range(str(value).strip().lower())
				except Exception:
					value = None
			if not isinstance(value, (list, tuple)) or len(value) != 2 or not value[0] or not value[1]:
				frappe.throw(frappe._("{0} needs a start and an end.").format(frappe.bold(op)), frappe.ValidationError, title=frappe._("Range needs two values"))
			value = (frappe.utils.getdate(value[0]), frappe.utils.getdate(value[1]))
		elif op != "is":
			if isinstance(value, (list, tuple, dict)):
				frappe.throw(frappe._("The value of {0} must be a single value.").format(frappe.bold(fieldname)), frappe.ValidationError, title=frappe._("Value must be single"))
			if op in ("like", "not like"):
				value = str(value or "")
				if "%" not in value:
					value = f"%{value}%"
			elif ftype == "Date" and value not in (None, ""):
				value = frappe.utils.getdate(value)
			value = "" if value is None else value
		yield i, str(fieldname).strip(), op, value, ftype


PLAIN_TYPES = ("Date", "Datetime", "Int", "Float", "Currency", "Check")  # columns that are never the empty string


def std_filters(doctype, filters, alias="", values=None, prefix="sf"):
	"""LEGACY (SQL text; the new API is filter_criteria). SQL conditions for a standard Frappe filter list.
	Returns (list of SQL strings, values)."""
	values = values if values is not None else {}
	out = []
	for i, fieldname, op, value, ftype in _parsed_filters(doctype, filters):
		col = column(doctype, fieldname, alias)
		key = f"{prefix}{i}"
		if op == "is":
			unset = f"({col} is null or {col} = '')" if ftype not in PLAIN_TYPES else f"{col} is null"
			out.append(unset if str(value).strip().lower() == "not set" else f"not {unset}")
		elif op in ("in", "not in"):
			values[key] = value
			out.append(f"ifnull({col}, '') {op} %({key})s")
		elif op in ("between", "timespan"):
			values[key + "a"], values[key + "b"] = value
			target = f"date({col})" if ftype == "Datetime" else col
			out.append(f"{target} between %({key}a)s and %({key}b)s")
		else:
			values[key] = value
			if op in ("=", "!=", "like", "not like") and ftype not in PLAIN_TYPES:
				out.append(f"ifnull({col}, '') {op} %({key})s")
			else:
				out.append(f"{col} {op} %({key})s")
	return out, values


def filter_criteria(doctype, filters, table):
	"""The standard filter list of a list screen as a list of pypika criteria over `table` (the DocType's own table,
	`frappe.qb.DocType(doctype)`, or a join of it). Same checks as ever: field names against the DocType's meta, values as parameters."""
	out = []
	for _i, fieldname, op, value, ftype in _parsed_filters(doctype, filters):
		col = table[fieldname]
		plain = ftype in PLAIN_TYPES
		if op == "is":
			unset = col.isnull() if plain else (col.isnull() | (col == ""))
			out.append(unset if str(value).strip().lower() == "not set" else ~unset)
		elif op in ("in", "not in"):
			out.append(fn.IfNull(col, "").isin(value) if op == "in" else fn.IfNull(col, "").notin(value))
		elif op in ("between", "timespan"):
			out.append((fn.Date(col) if ftype == "Datetime" else col).between(*value))
		else:
			left = col if plain or op not in ("=", "!=", "like", "not like") else fn.IfNull(col, "")
			out.append({"=": left == value, "!=": left != value, "<": left < value, ">": left > value, "<=": left <= value,
				">=": left >= value, "like": left.like(value), "not like": left.not_like(value)}[op])
	return out


def std_order(doctype, order_by, alias="", smart=None):
	"""LEGACY (SQL text; the new API is order_terms). An ORDER BY from a standard Frappe order_by string such as "due_date desc, title asc", or None.
	`smart` maps a field name to hand-written SQL (comma separated parts), used in place of the plain column."""
	if not order_by:
		return None
	parts = []
	for raw in str(order_by).split(",")[:5]:
		bits = raw.replace("`", "").strip().split()
		if not bits:
			continue
		fieldname = bits[0].split(".")[-1]
		way = "desc" if len(bits) > 1 and bits[1].lower() == "desc" else "asc"
		if len(bits) > 2 or (len(bits) == 2 and bits[1].lower() not in ("asc", "desc")):
			frappe.throw(frappe._("order_by must look like: fieldname asc, fieldname desc."), frappe.ValidationError, title=frappe._("Order by is malformed"))
		if smart and fieldname in smart:
			parts += [f"{p.strip()} {way}" for p in smart[fieldname].split(",")]
		else:
			parts.append(f"{column(doctype, fieldname, alias)} {way}")
	return ", ".join(parts) or None


def order_terms(doctype, order_by, table, smart=None):
	"""The standard Frappe order_by string ("due_date desc, title asc") as a list of (term, Order) for `apply_order`, or [].
	`smart` maps a field name to a function of the table that returns the terms to use instead of the plain column
	(for example a null-last date), each taking the way of the field."""
	if not order_by:
		return []
	out = []
	for raw in str(order_by).split(",")[:5]:
		bits = raw.replace("`", "").strip().split()
		if not bits:
			continue
		fieldname = bits[0].split(".")[-1]
		if len(bits) > 2 or (len(bits) == 2 and bits[1].lower() not in ("asc", "desc")):
			frappe.throw(frappe._("order_by must look like: fieldname asc, fieldname desc."), frappe.ValidationError, title=frappe._("Order by is malformed"))
		way = Order.desc if len(bits) > 1 and bits[1].lower() == "desc" else Order.asc
		if smart and fieldname in smart:
			out += [(term, way) for term in smart[fieldname](table)]
		else:
			column(doctype, fieldname)
			out.append((table[fieldname], way))
	return out


def sort_terms(sort, direction, allowed, table, default=()):
	"""The terms of a list's named sort (the `sort` and `dir` arguments). `allowed` maps the sort keys a caller may name to
	a function of the table that returns the terms; anything else gives `default` (a list of (term, Order))."""
	if not sort or sort not in allowed:
		return list(default)
	way = Order.desc if str(direction or "").lower() == "desc" else Order.asc
	return [(term, way) for term in allowed[sort](table)]


def apply_order(query, terms):
	for term, way in terms:
		query = query.orderby(term, order=way)
	return query


def null_last(field):
	"""Terms that put the rows with no value in `field` last: `lambda t: null_last(t.due_date)`."""
	return [field.isnull(), field]


def in_order_of(field, values):
	"""A term that sorts `field` by the position of its value in `values` (MariaDB FIELD)."""
	return fn.Function("FIELD", field, *values)


def extra_fields(doctype, fields, table, have=()):
	"""Columns the table view asks for on top of a list's own, as pypika fields of `table`. Unknown names are refused."""
	out, seen = [], set(have)
	for name in parse(fields, []) or []:
		name = str(name)
		if name in seen:
			continue
		column(doctype, name)
		seen.add(name)
		out.append(table[name])
	return out[:30]


def std_clause(doctype, filters, alias="", values=None):
	"""LEGACY (SQL text; the new API is filter_criteria). The standard filters as one string that starts with " and ", or "" when there are none."""
	conds, values = std_filters(doctype, filters, alias, values)
	return ((" and " + " and ".join(conds)) if conds else ""), values


def extra_columns(doctype, fields, alias="", have=()):
	"""LEGACY (SQL text; the new API is extra_fields). Columns the table view asks for on top of a list's own, as SQL select parts. Unknown names are refused."""
	out = []
	for name in parse(fields, []) or []:
		name = str(name)
		if name in have or name in [p.split("`")[-2] for p in out]:
			continue
		out.append(column(doctype, name, alias))
	return out[:30]


def tab_counts(base, values, tabs):
	"""LEGACY (SQL text; the new API is count_tabs). The count on each state tab of a list, in one query. `base` is the SQL from "from" to the end of the WHERE the list
	uses, without the condition on the tab's own field, so every count respects the other filters. `tabs` maps a tab to
	its SQL condition; None counts every row."""
	cols = ", ".join(("count(*)" if cond is None else f"ifnull(sum({cond}), 0)") + f" as `c{i}`" for i, cond in enumerate(tabs.values()))
	# nosemgrep: frappe-sql-format-injection -- `base` and the tab conditions are fixed SQL from the list methods; values are parameters
	row = frappe.db.sql(f"select {cols} {base}", values)[0]
	return {key: int(n or 0) for key, n in zip(tabs, row)}


AGGREGATES = ("count", "sum", "avg", "min", "max")


def summarise(doctype, base, values, alias, summary, start=0, page_length=20):
	"""LEGACY (SQL text; the new API is group_summary). One row per group for the library's Group By control, inside the same WHERE as the list it belongs to.
	`base` is the SQL from "from" to the end of the WHERE. `summary` is {fields, aggregates, order_by, totals}:
	fields are DocType fields, aggregates are {function, fieldname}, and an aggregate comes back as `_aggregate_<n>`."""
	summary = parse(summary, {}) or {}
	fields = [str(f) for f in (summary.get("fields") or [])][:3]
	if not fields:
		frappe.throw(frappe._("A summary needs at least one field to group by."), frappe.ValidationError, title=frappe._("Summary needs a group"))
	cols = [column(doctype, f, alias) for f in fields]
	aggs = []
	for i, a in enumerate((summary.get("aggregates") or [])[:6]):
		fn = str((a or {}).get("function") or "").lower()
		if fn not in AGGREGATES:
			frappe.throw(frappe._("Unknown aggregate {0}.").format(frappe.bold(fn)), frappe.ValidationError, title=frappe._("Unknown aggregate"))
		expr = "count(*)" if fn == "count" else f"{fn}({column(doctype, a.get('fieldname'), alias)})"
		aggs.append(f"{expr} as `_aggregate_{i}`")
	order = []
	for raw in str(summary.get("order_by") or "").split(","):
		bits = raw.replace("`", "").strip().split()
		if not bits:
			continue
		way = "desc" if len(bits) > 1 and bits[1].lower() == "desc" else "asc"
		name = bits[0].split(".")[-1]
		if name.startswith("_aggregate_") and name[11:].isdigit() and int(name[11:]) < len(aggs):
			order.append(f"`{name}` {way}")
		elif name in fields:
			order.append(f"{cols[fields.index(name)]} {way}")
	order = order or ([f"`_aggregate_0` desc"] if aggs else []) + [f"{c} asc" for c in cols]
	select = ", ".join([f"{c} as `{f}`" for c, f in zip(cols, fields)] + aggs)
	group = ", ".join(cols)
	start, page_length = page(start, page_length)
	# nosemgrep: frappe-sql-format-injection -- columns pass column() (DocType meta), aggregates an allowlist, `base` is fixed SQL; values are parameters
	rows = frappe.db.sql(f"select {select} {base} group by {group} order by {', '.join(order)} limit %(g_start)s, %(g_len)s",
		{**values, "g_start": start, "g_len": page_length}, as_dict=True)
	total = frappe.db.sql(f"select count(*) from (select 1 as one {base} group by {group}) g", values)[0][0]  # nosemgrep: frappe-sql-format-injection -- as above
	meta = frappe.get_meta(doctype)
	for f in fields:  # a Link shows the title of the record it points to
		field = meta.get_field(f)
		target = field.options if field and field.fieldtype == "Link" else {"area": "Life Area", "goal": "Life Goal"}.get(f) if doctype == "Life Index" else None
		title = target and frappe.get_meta(target).title_field
		if title:
			names = names_map(target, [r[f] for r in rows], title)
			for r in rows:
				r[f + "__label"] = names.get(r[f])
	for r in rows:
		for k, v in r.items():
			if hasattr(v, "isoformat"):
				r[k] = str(v)
	totals = None
	if aggs and flag(summary.get("totals")):
		totals = frappe.db.sql(f"select {', '.join(aggs)} {base}", values, as_dict=True)[0]  # nosemgrep: frappe-sql-format-injection -- allowlisted aggregates over meta-checked columns
	return {"rows": rows, "total": total, "totals": totals}


def list_query(doctype, fields, where=(), terms=()):
	"""A permission-checked select of `fields` (names, or terms) from the DocType with the criteria and the order applied.
	Join other tables on the result (`.left_join(x).on(...)`, `.select(...)`); only the DocType's own columns go in `fields`."""
	table = frappe.qb.DocType(doctype)
	query = frappe.qb.get_query(doctype, fields=[table[f] if isinstance(f, str) else f for f in fields], ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	return apply_order(query, terms)


def count_by(doctype, field, where=()):
	"""{value of `field`: rows} over the DocType's rows the user may read that meet the criteria."""
	table = frappe.qb.DocType(doctype)
	query = frappe.qb.get_query(doctype, fields=[table[field], fn.Count("*")], ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	return dict(query.groupby(table[field]).run())


def count_tabs(doctype, where, tabs):
	"""The count on each state tab of a list, in one query. `where` is the list's criteria without the one on the tab's own
	field, so every count respects the other filters. `tabs` maps a tab to its criterion (a function of nothing: build it
	over `frappe.qb.DocType(doctype)`); None counts every row."""
	table = frappe.qb.DocType(doctype)
	cols = [fn.Count("*") if crit is None else fn.IfNull(fn.Sum(Case().when(crit, 1).else_(0)), 0) for crit in tabs.values()]
	query = frappe.qb.get_query(doctype, fields=cols, ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	row = query.run()[0]
	return {key: int(n or 0) for key, n in zip(tabs, row)}


def group_summary(doctype, where, summary, start=0, page_length=20):
	"""One row per group for the library's Group By control, inside the same criteria as the list it belongs to.
	`where` is the list's criteria over `frappe.qb.DocType(doctype)`. `summary` is {fields, aggregates, order_by, totals}:
	fields are DocType fields, aggregates are {function, fieldname}, and an aggregate comes back as `_aggregate_<n>`."""
	summary = parse(summary, {}) or {}
	fields = [str(f) for f in (summary.get("fields") or [])][:3]
	if not fields:
		frappe.throw(frappe._("A summary needs at least one field to group by."), frappe.ValidationError, title=frappe._("Summary needs a group"))
	table = frappe.qb.DocType(doctype)
	cols = []
	for f in fields:
		column(doctype, f)
		cols.append(table[f])
	aggs = []
	for i, a in enumerate((summary.get("aggregates") or [])[:6]):
		name = str((a or {}).get("function") or "").lower()
		if name not in AGGREGATES:
			frappe.throw(frappe._("Unknown aggregate {0}.").format(frappe.bold(name)), frappe.ValidationError, title=frappe._("Unknown aggregate"))
		if name == "count":
			aggs.append(fn.Count("*").as_(f"_aggregate_{i}"))
		else:
			column(doctype, a.get("fieldname"))
			aggs.append({"sum": fn.Sum, "avg": fn.Avg, "min": fn.Min, "max": fn.Max}[name](table[str(a["fieldname"]).strip()]).as_(f"_aggregate_{i}"))
	order = []
	for raw in str(summary.get("order_by") or "").split(","):
		bits = raw.replace("`", "").strip().split()
		if not bits:
			continue
		way = Order.desc if len(bits) > 1 and bits[1].lower() == "desc" else Order.asc
		name = bits[0].split(".")[-1]
		if name.startswith("_aggregate_") and name[11:].isdigit() and int(name[11:]) < len(aggs):
			order.append((aggs[int(name[11:])], way))
		elif name in fields:
			order.append((cols[fields.index(name)], way))
	order = order or ([(aggs[0], Order.desc)] if aggs else []) + [(c, Order.asc) for c in cols]
	start, page_length = page(start, page_length)
	query = frappe.qb.get_query(doctype, fields=[c.as_(f) for c, f in zip(cols, fields)] + aggs, ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	rows = apply_order(query.groupby(*cols), order).limit(page_length).offset(start).run(as_dict=True)
	groups = frappe.qb.get_query(doctype, fields=cols, ignore_permissions=False)
	for crit in where:
		groups = groups.where(crit)
	total = frappe.qb.from_(groups.groupby(*cols).as_("g")).select(fn.Count("*")).run()[0][0]
	meta = frappe.get_meta(doctype)
	for f in fields:  # a Link shows the title of the record it points to
		field = meta.get_field(f)
		target = field.options if field and field.fieldtype == "Link" else {"area": "Life Area", "goal": "Life Goal"}.get(f) if doctype == "Life Index" else None
		title = target and frappe.get_meta(target).title_field
		if title:
			names = names_map(target, [r[f] for r in rows], title)
			for r in rows:
				r[f + "__label"] = names.get(r[f])
	for r in rows:
		for k, v in r.items():
			if hasattr(v, "isoformat"):
				r[k] = str(v)
	totals = None
	if aggs and flag(summary.get("totals")):
		sums = frappe.qb.get_query(doctype, fields=aggs, ignore_permissions=False)
		for crit in where:
			sums = sums.where(crit)
		totals = sums.run(as_dict=True)[0]
	return {"rows": rows, "total": total, "totals": totals}


def in_area(space, area, doctype, names):
	"""The names among `names` filed under the area, a sub-area, or listing one in "also in" (the lens on a set already
	read). Returns every name when there is no area."""
	names = [n for n in set(names or []) if n]
	if not area or not names:
		return set(names)
	if doctype not in ALSO_IN and doctype not in ("Life Goal", "Life Habit", "Life Insight"):
		frappe.throw(frappe._("Unknown filed DocType {0}.").format(doctype), title=frappe._("Unknown filed DocType"))
	x = frappe.qb.DocType(doctype)
	crit = area_criterion(space, area, x, also_in=doctype if doctype in ALSO_IN else None)
	return set(frappe.qb.from_(x).select(x.name).where(x.name.isin(names) & crit).run(pluck=True))  # system: the lens narrows a set the caller already read
