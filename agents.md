# Antigravity — Code Instructions

These are mandatory instructions for **all code** generated or modified in any project.
Every file, function, and line must comply with these standards.
This document is project-agnostic and should be reusable across all repositories.

---

## 0. General Principles

- **Stability**: Changes must never break existing functionality. Always verify that original code still works correctly after modifications.
- **Minimalist Code**: Always prioritize the smallest effective change. When adding new functionality, achieve the goal with the minimum number of lines possible without sacrificing readability or robustness. Avoid over-engineering.
- **Atomic Tasks**: Break down complex user requests into smaller, manageable sub-tasks. Document these in `task.md` and execute them one by one.
- **Deep Issue Analysis**: If an issue or bug is identified or suggested, do not apply a surface-level fix. Analyze the entire codebase to understand the root cause and propose/implement a solution that addresses the core of the problem.

---

## 1. Deep Research & Production-Ready Planning

**For every task or user prompt, you MUST prioritize research and planning:**

- **Mandatory Web Search**: Use `web_search` and `read_url_content` to perform deep research into the best industry standards, libraries, and architectural patterns relevant to the request.
- **Production-Ready Evaluation**: Every change must be designed for a production environment. Ask yourself: *"Is this implementation secure, scalable, and the most robust solution for this codebase?"*
- **Implementation Plan**: You MUST create a detailed implementation plan (e.g., in `implementation_plan.md`) for every change. Document the researched best practices and the rationale behind your technical decisions.
- **Validation**: Ensure your plan is the "best fit" for the existing architecture, avoiding ad-hoc solutions or over-engineering.

---

## 2. Pylint Compliance (Non-Negotiable)

**Every Python file must score 10.00/10.00 on Pylint** using the project's `pylintrc`. No exceptions.

### Hard Limits

| Rule | Limit |
|------|-------|
| Max line length | **120 characters** |
| Max function arguments | **6** |
| Max local variables per function | **15** |
| Max return statements | **6** |
| Max branches (if/elif/else) | **12** |
| Max statements per function | **50** |
| Max module lines | **700** |
| Max class attributes | **10** |
| Max parent classes | **7** |

### Absolutely Forbidden

- **Inline pylint disables** — never write `# pylint: disable=...` anywhere. If pylint complains, fix the code, don't suppress the warning.
- **Wildcard imports** — never write `from module import *`.
- **`print()` for logging** — use `logging.getLogger(__name__)` instead.
- **Old-style string formatting** — always use f-strings. No `%` or `.format()`.
- **Names**: never use `foo`, `bar`, `baz`, `tmp`, or `test` as variable names.

### Always Use

- **f-strings** for all string formatting.
- **`with` statements** for all context managers (files, locks, connections).
- **Dict/set comprehensions** where they improve clarity.
- **4-space indentation** everywhere, no tabs.

---

## 3. Code Clarity — Write for Humans First

Code is read 10x more than it is written. Every piece of code must be **immediately understandable** by a developer seeing it for the first time.

### Naming

- **Functions**: verb-first, descriptive — `build_system_instruction()`, not `sys_inst()`.
- **Variables**: immediately obvious purpose — `customer_phone`, not `cp` or `phone1`.
- **Booleans**: read like a question — `is_active`, `has_expired`, `should_retry`.
- **Constants**: `UPPER_SNAKE_CASE` with a comment explaining *why* that value — not just *what* it is.
  ```python
  # Timeout set to 30s because the average API response is 2-5s;
  # 30s accounts for retries and network jitter
  REQUEST_TIMEOUT = 30
  ```
- **Allowed short names**: `i`, `j`, `k` (loop counters), `ex` (exceptions), `_` (throwaway), `pk`, `id`.

### Structure

- **One function = one job**. If a function does two things, split it.
- **Keep functions short** — if it doesn't fit on one screen (~40 lines), it's too long. Extract helpers.
- **Group related code** with clear section headers:
  ```python
  # ──────────────────────────────────────────────
  # Database Helpers
  # ──────────────────────────────────────────────
  ```
- **Logical ordering within files**:
  1. Module docstring
  2. Imports (stdlib → third-party → local, separated by blank lines)
  3. Constants
  4. Helper/utility functions
  5. Main classes or core functions
  6. Entry point (`if __name__ == "__main__"`)

### Comments

- **Don't comment *what*. Comment *why*.**
  ```python
  # BAD: Set timeout to 30
  timeout = 30

  # GOOD: 30s accounts for up to 3 retries with exponential backoff
  timeout = 30
  ```
- **Explain non-obvious decisions** — thresholds, delays, workarounds, protocol quirks.
- **Use inline comments sparingly** — if code needs a lot of inline comments, the code itself isn't clear enough. Refactor.

---

## 4. Security

### Secrets Management
- **Never hardcode secrets** — API keys, passwords, tokens, database URIs must always come from `.env` files or environment variables.
- **Never commit `.env` files** — ensure `.gitignore` includes `.env`, `.env.*`.
- Use `os.getenv("KEY")` or a library like `python-dotenv` to load secrets.
  ```python
  # BAD
  API_KEY = "sk-abc123..."

  # GOOD
  API_KEY = os.getenv("API_KEY")
  ```

### Input Validation
- **Validate all external inputs** before processing — API request payloads, WebSocket messages, query parameters, file uploads.
- Never trust user input. Check types, ranges, lengths, and formats.
- Use Pydantic models or explicit validation for REST endpoint bodies.
  ```python
  # BAD — trusting raw input
  phone = request.get("phone")
  send_sms(phone)

  # GOOD — validate first
  phone = request.get("phone", "")
  if not phone or not phone.isdigit() or len(phone) != 10:
      raise ValueError("Invalid phone number")
  ```

### Log Sanitization
- **Never log sensitive data in plain text** — API keys, passwords, auth tokens, customer phone numbers, email addresses, or any PII.
- Mask or redact sensitive fields before logging.
  ```python
  # BAD
  logger.info(f"Calling customer: {phone_number}")

  # GOOD
  logger.info(f"Calling customer: ***{phone_number[-4:]}")
  ```

---

## 5. Robustness & Error Handling

- **Handle edge cases explicitly** — empty inputs, None values, zero-length data, missing dict keys.
- **Use `.get()` with defaults** for dictionaries instead of bare `[]` access where the key might be absent.
- **Log errors with context** — include request IDs, entity identifiers, or other traceable info.
- **Fail gracefully** — catch specific exceptions, log them, and degrade. Never bare `except:`.
  ```python
  # BAD
  except:
      pass

  # GOOD
  except ConnectionError as exc:
      logger.error(f"[API] Connection failed for request {request_id}: {exc}")
  ```

---

## 6. Logging Standards

- Use `logging.getLogger(__name__)` at module level.
- **Format**: `[ACTION] Key: value | Key: value`
  ```python
  logger.info(f"[USER_CREATED] User: {user_id} | Role: {role}")
  logger.warning(f"[RATE_LIMIT] IP: {masked_ip} | Retry after: {retry_after}s")
  ```
- Use appropriate log levels:
  - `DEBUG` — internal state, detailed traces, timing info
  - `INFO` — lifecycle events, successful operations, connections
  - `WARNING` — recoverable issues, retries, deprecation notices
  - `ERROR` — failures that affect functionality
- **Remember**: never log PII or secrets (see Section 3).

---

## 7. Documentation

### README Maintenance
- **Update `README.md` whenever**:
  - A new module or package is added
  - Setup steps change (new dependencies, env vars, config)
  - The project structure changes significantly
- The README should always reflect the **current** state of the project, not a past version.

### API Documentation
- **Document all REST endpoints** with:
  - HTTP method and path
  - Request body schema (with types and required/optional)
  - Response schema (with status codes)
  - Example `curl` or request snippet
- Keep API docs in the README or a dedicated `docs/api.md` depending on project size.

### Changelog
- **Maintain a `CHANGELOG.md`** at the project root.
- Log all significant changes: new features, breaking changes, bug fixes, dependency updates.
- Follow a simple format:
  ```markdown
  ## [YYYY-MM-DD]
  ### Added
  - New endpoint `/api/v1/users` for user management

  ### Changed
  - Increased request timeout from 10s to 30s

  ### Fixed
  - Fixed race condition in WebSocket disconnect handling
  ```

---

## 8. Output Quality Enrichment

When generating code, always aim for **production-grade** output:

- **Type hints** on all function signatures (args and return types).
- **Docstrings** on any function with non-obvious behaviour:
  ```python
  def fetch_user(user_id: str, include_inactive: bool = False) -> dict | None:
      """
      Fetch a user record from the database.

      Args:
          user_id: Unique identifier for the user
          include_inactive: If True, also return soft-deleted users

      Returns:
          User dict if found, None otherwise
      """
  ```
- **Guard clauses** at function start rather than deep nesting:
  ```python
  # BAD
  def process(data):
      if data:
          if data.get("payload"):
              # ... deeply nested logic

  # GOOD
  def process(data):
      if not data or not data.get("payload"):
          return None
      # ... clean, flat logic
  ```
- **Consistent error messages** — every log or error message should be clear enough to debug from logs alone.
- **No dead code** — remove commented-out code, unused imports, and obsolete functions. Keep the codebase clean.

---

## 9. Pre-Submission Checklist

Before considering any code change complete:

1. ✅ Pylint score is **10.00/10.00** (`pylint *.py --rcfile=pylintrc`)
2. ✅ No `# pylint: disable` comments anywhere
3. ✅ All functions have type hints
4. ✅ Complex logic has *why* comments
5. ✅ Variable names are self-documenting
6. ✅ No bare `except:` blocks
7. ✅ Logging uses the `[ACTION] Key: value` format
8. ✅ No secrets or PII in code or logs
9. ✅ External inputs are validated before use
10. ✅ README / CHANGELOG updated if applicable
11. ✅ Code reads cleanly top-to-bottom without jumping around
12. ✅ **Minimalist & Concise**: functionality achieved with the fewest possible lines without sacrificing readability.
13. ✅ **Documentation Auto-Update**: If any structural or major functional code changes are made, ensure that `.agents/temp_documentations/workflow.md` and `.agents/temp_documentations/function.md` are automatically updated to reflect the new functionality.
14. ✅ **Production-Ready & Researched**: The implementation follows the researched best practices and is verified to be the most robust solution for the codebase.
15. ✅ **Clean Workspace**: Any temporary files, scratch scripts, or verification tests created during the task (e.g., `tests/verify_*`, `tmp/*`) must be automatically deleted once they are no longer needed for the final submission.

---

## 10. Continuous Documentation Updates

To maintain a clear and up-to-date understanding of the software's architecture and logic, **every time** any significant change is made to the codebase (such as adding a new module, removing an old feature, or modifying an existing workflow), you **MUST auto-update** the following two files located in `.agents/temp_documentations/`:

1. **`workflow.md`**: Update this file to reflect any new end-to-end flows, sequence changes, intent classification modifications, or changes to the RAG ingestion structure.
2. **`function.md`**: Update this file when adding new critical functions, deleting deprecated ones, or changing the core purpose of a file. The explanations must remain high-level and in "very simple terms" focusing on the big-picture role rather than line-by-line syntax.

---

## graphify

This project uses **graphify** to maintain a persistent knowledge graph of the system architecture and workflows. All agents MUST prioritize this graph over manual codebase exploration.

Rules:
- **Mandatory Context**: Before answering architecture questions or making changes, read `graphify-out/GRAPH_REPORT.md` to understand core workflows, "god nodes", and community structures.
- **Efficient Discovery**: Utilize `graphify` tools (MCP tools like `query_graph` or CLI commands like `graphify query "<question>"` and `graphify explain "<concept>"`) to identify the specific files and functions relevant to your task. Avoid using `grep` or `list_dir` for broad codebase exploration.
- **Workflow Navigation**: Use `graphify path "A" "B"` to trace data flows and logic between components.
- **Documentation**: If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw source files to get a high-level understanding of the logic.
- **Graph Maintenance**: After modifying code files, run `graphify update .` to keep the knowledge graph current (AST-only, no API cost).