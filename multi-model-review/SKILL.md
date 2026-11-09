---
name: multi-model-review
description: Independent poll of Codex Sol, DeepSeek, Gemini and Grok for architecture decisions, review of specs, plans and important code, and hard bugs
---

# Polling several models

When: choosing an architecture or approach where a mistake is expensive; reviewing specs, plans and important code; hard bugs whose cause was not found on the first try. Not for small edits or simple questions.

1. Write one brief, in English: facts, options, answer format, sources as paths. Do not reveal your own choice. Ask for the answer in the user's language and for the final answer after a line `=== ANSWER ===`. While the poll runs, do not write your own conclusions into files the models can read (journals, checklists, READMEs): they would see them and stop being independent. Write them after the poll.
2. Run in parallel, read-only. Put each model in its own terminal tab of the app (`open_terminal_tab`, `run_in_terminal`) so the user can watch it work, and pipe through `tee` so the output goes to the screen and to a `<log>` file:
   - Codex: `codex exec -m gpt-6.1-sol -s read-only --skip-git-repo-check -C <repo> -o <answer> - < <brief> 2>&1 | tee <log>`
   - DeepSeek: `~/.opencode/bin/opencode run -m 'deepseek/deepseek-flash#max' --title "<topic>" "$(cat <brief>)" 2>&1 | tee <log>`. The log holds the whole work trace; the answer is everything after the last `=== ANSWER ===` line: `awk '/=== ANSWER ===/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' <log> > <answer>`.
   - Grok: `cursor-agent -p --mode ask --model grok-4.7-high --workspace <repo> "$(cat <brief>)" 2>&1 | tee <answer>`
   - Gemini: needs a **separate copy of the brief**, because in `plan` mode the terminal and file reading are forbidden. First line of the copy: "You have no access to files or a terminal. Do not call any tools. Answer only from the text below. Anything you cannot see goes under 'not verified'." Remove words like "read" and "check in the code" from the copy, and paste the text of the needed files (journal tails, code) at the end. Run: `agy -p "$(cat <gemini-brief>)" --mode plan --model gemini-3.8-flash-high --print-timeout 0 2>&1 | tee <answer>`.
3. Do not use a fixed time limit. While waiting, look at what each model is doing: `tail -n 20 <log>` and `ls -l <log>` (size and modification time). A model that is working keeps adding lines, and its last lines show real steps (files read, commands run, notes), so keep waiting however long it takes. Judge it stuck only if the log has not changed for about 5 minutes, or it repeats the same action or error, or its steps drift away from the brief. Then stop it (Ctrl+C in its tab), say what you saw in the log, and tell the user. Grok in `-p` mode prints almost nothing until it finishes, so an empty file does not mean stuck: check that its process is alive (`pgrep -fl cursor-agent`).
4. Before reading an answer, check it: the file is not empty and does not contain "no output produced", "permission", "denied" or "error". An exit code is not a sign of success: `agy` returned 0 with an empty answer. If a model did not run, say so; do not replace it silently.
5. Check the key claims against the primary source: code, git, documentation, a test run. A majority vote is not evidence. Example: Gemini wrote "not committed" when the commit already existed, because it read a stale journal line.
6. Give a table "model — choice — main remark" and a recommendation. Note whether each model could see your conclusions in the repository.

Task files go to OpenAI, DeepSeek, Google and Cursor/xAI. Do not send keys or personal data. For work or private projects, ask the user first.

Project rules come first: if the project's CLAUDE.md forbids sending something out or names its own executors, follow it. A poll costs time and limits, so do not run all four models without need: two are enough for a small review.
