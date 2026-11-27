"""Running a command for the updater, and saying why it failed (issue 138).

A failed command is written to the log with the command itself (secrets hidden), its exit code and the last lines of what it
printed on stdout and on stderr; never just "exited 1:". Nothing here goes through a shell."""
import re
import subprocess
from types import SimpleNamespace

SECRET = re.compile(r"(secret|token|password|passwd|api[_-]?key|authorization|bearer)", re.I)
URL_LOGIN = re.compile(r"(//)[^/@\s]+@")
TAIL = 10
LIMIT = 3000


class StepError(RuntimeError):
	"""A failure whose message is already safe to log: it is written as it is."""


def scrub(text, tail=TAIL) -> str:
	"""The last `tail` lines of a text, without any line that looks like it holds a secret or a login in a URL."""
	lines = [URL_LOGIN.sub(r"\1", x.rstrip()) for x in str(text or "").splitlines() if x.strip() and not SECRET.search(x)]
	return "\n".join(lines[-tail:])


def command_text(argv) -> str:
	return " ".join("…" if SECRET.search(str(a)) else str(a) for a in argv)


def failure(argv, code, stdout="", stderr="") -> str:
	"""`<command>` exit N, then the last lines of stdout and of stderr, or 'no output'."""
	out, err = scrub(stdout), scrub(stderr)
	head = f"`{command_text(argv)}` exit {code}"
	if not out and not err:
		return f"{head}, no output"
	parts = [head]
	if out:
		parts.append("stdout (last lines):\n" + out)
	if err:
		parts.append("stderr (last lines):\n" + err)
	return "\n".join(parts)[:LIMIT]


def run(argv, cwd=None, timeout=3600, text_in=None, env=None):
	"""Run a fixed argument list. Never raises: a command that cannot start or times out answers with a non-zero returncode."""
	try:
		return subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, timeout=timeout, input=text_in,  # noqa: S603 -- fixed arguments
			stdin=None if text_in is not None else subprocess.DEVNULL, env=env, check=False)
	except subprocess.TimeoutExpired:
		return SimpleNamespace(returncode=124, stdout="", stderr=f"timed out after {timeout} seconds")
	except OSError as e:
		return SimpleNamespace(returncode=127, stdout="", stderr=f"did not run: {type(e).__name__}")
