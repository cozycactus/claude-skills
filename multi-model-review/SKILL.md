---
name: multi-model-review
description: Independent poll of Codex Sol, DeepSeek, Gemini and Grok for architecture decisions, review of specs, plans and important code, and hard bugs
---

# Polling several models

When: choosing an architecture or approach where a mistake is expensive; reviewing specs, plans and important code; hard bugs whose cause was not found on the first try. Not for small edits or simple questions.

All mechanics are in `poll.py` next to this file. Below, `P` is shorthand for `python3 ~/.claude/skills/multi-model-review/poll.py` (write the full command; it is not an installed alias). Do not write the models' command lines by hand. `NOTES.md` in the same folder records what was observed and why each choice was made: read it only when something does not behave as described here.

0. **Before anything is sent.**
   - Project rules come first: if the project's CLAUDE.md forbids sending something out or names its own executors, follow it.
   - The polled folder and the brief go to the providers of the chosen models (OpenAI, Cursor/xAI, DeepSeek, Google). Never send keys or personal data. For work or private projects ask the user first, unless they already asked for this poll on this project.
   - Choose the models before launch. Default: `codex,grok`, both on a plan. Add `deepseek` and `gemini`, both billed per token, when the user asks for all models or the decision is expensive to get wrong. Cost grows with what a model reads; ask the user before adding a per-token model on a big folder. Never replace a model with another one silently.
   - Choose the folder to send: the smallest one that holds what the reviewers need. If `poll.py` refuses it as too large, narrow the folder; `--force-large` only after the user agrees.
   - While a poll runs, write your own conclusions nowhere the reviewers can read: not in the polled folder, not in the scratchpad, not elsewhere on disk (Codex reads the whole disk, Gemini reads the scratchpad). If conclusions were already written in the folder before the poll, say so in the report.

1. **Brief.** One file, in English: facts, options, what to review, the answer format, and the user's language for the answer. Name files by their path inside the folder. Do not reveal your own choice. Leave out the answer-marker rule and anything about read-only or throwaway copies: `poll.py` appends those per model.

2. **Set up.** `P new --src <folder> --brief <file> --models <list> [--run codex] [--attach <file>] [--topic <word>]`
   - Every model gets its own private snapshot of the folder's current files; nothing is written to the user's folder. The snapshots have no git history and no diff of uncommitted work. When the review is about a change, make the diff with `P diff --src <folder> [--base <commit>] > <scratchpad file>` (not with plain `git diff`, which runs whatever the repository's config names), check it for secrets, and pass it with `--attach`.
   - `--run codex` when the thing under review can be run (a test, a simulation, a check script): Codex may then change files and run commands in its copy, with no network. A reviewer that only reads cannot reproduce its own claims. DeepSeek can always run things in its copy; Grok only reads. `--run gemini` removes Gemini's read-only policy while its API key and open network stay: use it only when the user agreed to exactly that.
   - In a git project the files git ignores stay out of the copies, so tools from a `.venv` or downloaded models are missing: say in the brief what cannot be run. In a folder that is not a git project (the output says `plain`), `.gitignore` is not applied.
   - The command prints the poll folder, notes, a launch command per model, and what each model can access. Keep that output for the report.
   - **Before launching, read the poll's `manifest.txt`**: the files copied, and what was left out (names that look like secrets, links leading outside, nested repositories, standard folders such as `node_modules`). The secrets filter goes by file name only, so look for anything private yourself. If something should not be sent, or something the reviewers need is missing, stop: `P clean <poll> --all`, then fix the folder choice or tell the user.

3. **Launch.** Each printed line that starts with `python3` goes, exactly as printed, into its own terminal tab with `run_in_terminal`, using the session's working directory as the tab's directory. The app allows six of your tabs at a time: close a model's tab once its answer is taken.

4. **Wait.** Run `P status <poll>` right after launch, then `P wait <poll>` repeatedly: it returns when a model ends or after four minutes, and prints the status table (give the Bash call a timeout of five minutes). Act on the `hint` column. There is no time limit, and silence alone is never a reason to stop a model: one that thinks can be quiet for many minutes. Stop a model only when it ended with an error, keeps repeating the same failing step, shows a lost connection and no activity since, or has clearly left the task; tell the user what you saw, then `P stop <poll> <model>`. Past 45 minutes, ask the user whether to keep waiting.

5. **Answers.** `P answers <poll>` checks every run and writes `<poll>/<model>/answer.md` (plus `notes.md` for work notes). Read every answer in full. `NO MARKER` and `MARKER LAST` mean the model did not mark its final answer the expected way: the text was kept, read it and decide whether it is a finished answer. `FAILED` and unfinished runs are reported as such; whatever a failed run wrote is in `partial.md` as evidence, not as an answer. Retry a model once, in a new poll, only when the reason was a start-up problem you fixed (a missing key, not signed in).

6. **Verify.** Check the key claims against the primary source: code, git, documentation, a test run. A majority is not evidence, and models state guesses as facts. Reproduce in a model's copy or, once all answers are taken, in the scratchpad; never in the user's folder.

7. **Report.** Per model: finished or failed, ran things or only read, what it could access (from the `new` output), its main finding or choice. Then the important claims as confirmed, refuted or not verified, and your recommendation. State the limits of independence: whether reviewers could see your conclusions, and that Codex can technically read the other reviewers' folders. End with the table from `P usage <poll>`. A `?` stays a `?`; do not guess the number.

8. **Clean.** After the report: `P clean <poll>` deletes the copies and keeps the briefs, logs and answers in `~/.claude/polls/`.

What each model can reach is printed by `P new` and belongs in the report. In short: the user's folder is never written to. Codex's commands have no network, but it can read the whole disk. Grok runs sandboxed with a home folder of its own and sees none of the user's. DeepSeek is sandboxed too; with a keychain item `deepseek-api-key` it gets data folders of its own, without one it shares opencode's real data folder, which holds the user's earlier opencode sessions (the `new` output says which). Gemini's sandbox still shows it `~/.config` and the temp areas, and it carries its own API key. DeepSeek, Grok and Gemini have open network.
