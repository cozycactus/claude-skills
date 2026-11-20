# multi-model-review: observations and reasons

Not loaded with the skill. Read it when `poll.py` misbehaves, a CLI was updated, or a rule in SKILL.md looks wrong.

These are the author's observations, not a security certificate. They were made on 2026-11-11 on macOS (Apple silicon) with codex-cli 0.167.0, opencode 2.2.6, cursor-agent 2026.11.11, Gemini CLI 0.68.0. "Seen" means observed in a real run that day. On 2026-11-18 Codex moved to `gpt-6.2-astra` at `max`, Grok to `grok-4.7-xhigh` and Gemini to `gemini-4-hydrogen`; on 2026-11-20 Gemini moved on to `gemini-4-neon` (launched 2026-11-18, twice Hydrogen's price). The Gemini read-only checks below were made with `gemini-4-carbon` and were never repeated on Hydrogen; check 1 of the last section was repeated on Neon on 2026-11-20, still with Gemini CLI 0.68.0 (result in the table below). Not repeated on Neon: `--run` mode and the "Policy file error" line. Gemini CLI 0.68.0 has no option for the thinking level and does not know Neon (its bundle names only `gemini-4-argon`; the id is passed through), so Neon runs at whatever the API defaults to; that default and the levels the API accepts were not verified here. A new CLI version can change any of it: re-run the checks in the last section after an update.

## How each model is started (`poll.py launch`)

| Model | Command | Seen |
| --- | --- | --- |
| Codex | `codex exec --ignore-user-config -m gpt-6.2-astra -c model_reasoning_effort="max" -c sandbox_workspace_write.exclude_slash_tmp=true -s read-only\|workspace-write --skip-git-repo-check -C <copy> -o <last message> -` with the brief on stdin | The trace on stderr shows `sandbox: read-only` or `workspace-write [workdir, $TMPDIR]` (without the `exclude_slash_tmp` setting it also listed `/tmp`), so `-s` wins over `sandbox_mode = "danger-full-access"` in the user's config. In read-only mode it inspected files with `cat` and ran no project code; with `--run` it ran a test before and after its own fix in the copy. |
| DeepSeek | `sandbox-exec -f <profile> ~/.opencode/bin/opencode --standalone run --format json -m 'deepseek/deepseek-flash#max' --title <poll id> <brief>` | With no sandbox it ran shell commands all over the home folder, read another reviewer's folder and wrote into a folder meant to be read-only. Inside the profile: wrote and ran in its copy; `touch` in the home folder and in `/opt/homebrew`, `cat` of a file in `~/Documents` and `ls ~` all gave "Operation not permitted"; `python3` and `node` ran. `--standalone` is required: otherwise tools run in opencode's background service, outside the sandbox. |
| Grok | `sandbox-exec -f <profile> cursor-agent -p --trust --mode ask --model grok-4.7-xhigh --output-format stream-json --workspace <copy> <brief>` | Grok itself reported that `ask` mode still lists Write, StrReplace and Shell tools and only instructs it not to use them, so the profile is the real limit. `--trust` is needed or `-p` exits with "Workspace Trust Required". `stream-json` prints its thinking, every tool call and the answer as they happen; with plain `json` it printed nothing until the end, and a run that hung after "Connection lost, reconnecting" looked the same as one that was thinking (54 minutes, 12 seconds of CPU). |
| Gemini, read-only | `SEATBELT_PROFILE=strict-open gemini --skip-trust --approval-mode plan --policy <temp copy of gemini-readonly.toml> -s -m gemini-4-neon -o stream-json -p <brief>` | Plain `--approval-mode plan` is NOT read-only in a headless run: the model called `exit_plan_mode`, the CLI auto-approved it ("Switching to YOLO mode"), and it then created a file and ran a shell command. With the allow-list policy the model was offered only read and search tools; asked to leave plan mode, write and run, it could do none of it. Repeated on `gemini-4-neon` on 2026-11-20 in a Gemini-only poll: the model reported six declared tools (`list_directory`, `read_file`, `grep_search`, `glob`, `google_web_search`, `update_topic`), called only `read_file` and `list_directory`, had no `exit_plan_mode`, write or shell tool to call, and its copy was unchanged (`git status` clean). |
| Gemini, `--run` | same with `--approval-mode yolo` and no policy | In the `strict-open` sandbox it wrote and ran `python3` in its copy; `touch` and `cat` in the home folder were refused; the keychain could not be read; `curl` returned 200 (network is open). |

The launcher starts each model with a short, fixed environment (HOME, USER, PATH, LANG, TERM, a temp folder, git told to ignore user config), so other exported secrets in the user's shell do not reach it. Gemini also gets `GEMINI_API_KEY`, which comes from the macOS keychain through `~/.zshrc`: it exists in a terminal tab and not in the Bash tool's shell. Never print it. A value passed this way was not visible in `ps` output in a test.

Why a Python launcher and not shell scripts: the first version generated `zsh` scripts, and review found that a leftover `$POLICY` in the user's shell made them delete an unrelated file, that stopping the script left the model running, and that a second run overwrote the first one's files. The launcher builds the argument list itself, runs the model in its own process group, and records pid, start time and exit result. It refuses a second launch of the same model in the same poll.

Stopping. Every two seconds the launcher notes the model's descendants with their start times, including ones that moved to another session or process group. On Ctrl-C, a closed tab or `poll.py stop` it sends Ctrl-C, then TERM after 8 seconds, then KILL after 16, to the group and to every noted process; when the model exits by itself, whatever it left running is stopped the same way. If the launcher fails after starting the model, the model is killed and the result is `launcher-error`. All of this was tested with stand-in commands (a child that ignores Ctrl-C, a grandchild, a process in its own session). What still escapes: a process that detaches and whose parent exits before the next two-second look.

Launch and clean share a file lock: every live launcher holds it, `clean` needs it alone, so a copy cannot be deleted under a starting or running model. If the launcher itself is killed while the model lives, `status` shows `orphaned`; `stop` still works on it and `clean` refuses until it is stopped.

## The sandbox profile for DeepSeek and Grok

Allow by default, then:
- writes: denied everywhere except the model's own temp folder and `/dev`, plus for DeepSeek its copy and opencode's data folders (`~/.local/share/opencode`, `~/.local/state/opencode`, `~/.cache/opencode`), and for Grok a home folder of its own inside the poll.
- reads: `/Users`, `/Volumes`, `/private/tmp` and `/private/var/folders` are denied, then the copy, the temp folder, the CLI's own program folder and a few tool folders under the home folder are allowed (`.local/bin`, `.local/share/uv`, `.local/opt`, `.hermes/node`, `.cargo/bin`, `.rustup/toolchains`, `.bun/bin`). Folders above the readable ones may be resolved but not listed; without that cursor-agent cannot even find its own binary.
- The programs themselves (`~/.opencode`, `~/.local/share/cursor-agent`) are read-only, so a model cannot replace the tool the user will run next time.

Grok's own home. cursor-agent is started with `HOME` set to `<poll>/grok/home`, which holds nothing but a link `Library/Keychains` to the real keychain folder; the profile lets it read `login.keychain-db` there (encrypted) and nothing else of the user's. Seen: it reports "Logged in", answers normally, and writes its state into that private home. With a fresh home and no keychain link it reports "Not logged in". So Grok sees neither `~/.cursor` nor the user's earlier Cursor chats.

Grok and long poll names. cursor-agent keeps a `worker.sock` for each workspace under `<data dir>/projects/<slug of the workspace path>` and wants the path short enough for a unix socket (104 bytes on macOS). Read in cursor-agent 2026.11.11: when `<data dir>/projects` is longer than 83 characters it tries `<data dir>`, then `$TMPDIR/.cursor`, then a fixed `/tmp/.cursor`, which the profile denies. Seen on 2026-11-20: polls with the topics `four-midi-outputs` and `four-midi-outputs-r2` died within seconds with "EPERM: operation not permitted, mkdir '/tmp/.cursor/…'", while `midi4` on the same source ran; by the code the limit under the real polls root was a topic of 15 characters for the slot `grok`, less for a variant slot (not tested directly). `poll.py` now sets `CURSOR_DATA_DIR=../home/.cursor`, a path relative to the copy, which is cursor-agent's working directory: the program uses the value as given, so the length test passes and the data stays where it was, in the private home. The profile is unchanged. Seen with a 33-character topic under a long polls root: Grok started, answered, and put `worker.sock` in `home/.cursor/projects/`; no `/tmp/.cursor` appeared. If a later cursor-agent resolves the variable to an absolute path, the same error comes back, so it fails closed.

DeepSeek's data. opencode keeps its DeepSeek sign-in inside `~/.local/share/opencode/opencode.db`, the same database that holds every earlier opencode session; with a fresh data folder and no key it could not sign in. So there are two modes, chosen by `poll.py new` and printed in its output:
- a keychain item `deepseek-api-key` exists: the launcher reads it and passes it as `DEEPSEEK_API_KEY` to that one process, and points `XDG_DATA_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` at `<poll>/deepseek/home`. The profile then names nothing of opencode's real data; only its program and config stay readable. Seen with a dummy key under a test item name: opencode used the key from the environment (DeepSeek answered 401), created its database in the private folder, and the real database was not touched. Then seen with the real key: the run finished normally, the real database's modification time did not change, canary writes to the real data folder and to the home folder did not happen, and the key text was in no file of the poll. Under the generated profile, listing or writing opencode's real data folder fails with "Operation not permitted". Two things to know: an authentication error from opencode prints the last four characters of the key, and the key sits in the model's environment, so a command the model runs could print it into its own log (the same holds for Gemini with `--run`).
- no such item: DeepSeek reads and writes opencode's real data folders, earlier sessions included.
To create the item: `security add-generic-password -U -a "$USER" -s deepseek-api-key -w` in a terminal, then paste a key from the DeepSeek platform.

The Gemini key is taken the same way when `GEMINI_API_KEY` is not in the environment (item `gemini-api-key`), so a Gemini launch also works from a shell that did not load `~/.zshrc`.

Checked directly with shell commands under the generated profiles: both read their copy; neither can read `~/Documents`, list `~/.cursor/chats`, or write to the home folder, `~/.cursor`, `/opt/homebrew` or `~/.opencode/bin`; Grok cannot write its copy or list opencode's data; DeepSeek can write its copy and list opencode's data. (That DeepSeek result is for the mode without the keychain item.) An earlier, looser profile denied writes only under the home folder, and a write to `/opt/homebrew` (owned by the user) succeeded.

`poll.py new` refuses a source folder that overlaps any CLI data folder (`~/.cursor`, `~/.codex`, `~/.gemini`, opencode's folders). Network is open for both models, and the profile does not stop them from starting processes. A tool that lives in another folder under the home folder will not run for DeepSeek: add its folder to `TOOL_DIRS` in `poll.py`.

## What cannot be closed

- Codex cannot be wrapped in an outer `sandbox-exec`: its own sandbox then fails with `sandbox_apply: Operation not permitted`. So Codex can read the whole disk, including the other reviewers' folders while they exist. The brief footer asks every model to stay inside its copy and to name any path it opened outside; that is a request, not a barrier. Not verified: whether Codex's `--permission-profile` / `denied_reads` can limit reads.
- Gemini's `strict-open` profile reads `~/.config`, `~/.gitconfig` and all of `/private` (which includes the coordinating agent's scratchpad), allows all outbound network, and its API key is in its environment. It cannot read `~/.claude/polls`, so it does not see the other reviewers.
- If Gemini fails to load the policy file it prints "Policy file error" and carries on without it. The launcher checks that the policy file parses, watches stderr for that line and sends KILL at once (result `policy-error`, within a second in a test). This is detection after the fact, not a guarantee: a tool call could slip in before the kill. What bounds the damage is the CLI's own sandbox, which keeps writes inside the throwaway copy; the policy is copied to the system temp folder because the CLI re-reads it inside its sandbox, which cannot read the skill folder or the poll folder.

## The copy

`poll.py new` builds one snapshot and clones it per model. It never writes to the source folder and runs git with no inherited `GIT_*` variables, no user config, no hooks and `core.fsmonitor` off (a repository's own config can name a program there, and git would run it).
- What is copied: the current files. In a git project, the files git tracks or would track (`git ls-files -co --exclude-standard`), so ignored files stay out. In a folder that is not a git project, or whose only git root is the home folder (true on this machine), everything except `node_modules`, `.venv` and caches; `.gitignore` is not applied there.
- The result is a fresh repository with one commit, "snapshot". No history, no remotes, no hooks, and no diff of uncommitted work. An earlier version also stored the original's last commit so that `git diff` worked in the copy; it was removed because deleted files stayed readable in that commit without appearing in the manifest, and the extra paths (archive, size limits, export-ignore, sparse checkouts) kept producing defects. A diff the reviewers need is made with `poll.py diff` and passed with `--attach`. `poll.py diff` runs git with the same restrictions as the copy step plus `--no-ext-diff --no-textconv`; a plain `git diff` in the user's repository would run a configured fsmonitor, external diff or textconv program.
- The source folder is opened once and files are reached from that handle without following links at any step, so neither a link inside it nor a swap of the folder itself can redirect the copy. A link is copied only if it points inside the folder, as a relative link. A link pointing outside is dropped, and so is everything under a folder that is itself a link (an earlier version copied an outside file that way; another wrote through a link into the source project).
- Left out by name: `.env*`, `.envrc`, `*.pem`, `*.key`, `*.p8`, `id_rsa*`, `*credentials*`, `*serviceaccount*`, `*.tfstate`, `*.tfvars`, folders named `secrets`, `.ssh`, `.aws` and similar. Names only: a key inside `settings.json` goes through. `manifest.txt` in the poll folder lists everything copied and everything left out, and the skill requires reading it before launch.
- Not copied, and reported: submodules and nested repositories, also when git still lists old paths inside a folder that has since become its own repository. In plain copies the skipped standard folders are listed in the manifest.
- A folder with a `.git` that git cannot read is refused rather than copied as a plain folder.
- Refused: the home folder or anything containing it, a folder that contains or sits inside `~/.claude/polls`, more than 20,000 files or 300 MB (override with `--force-large`).

## Answers

- The marker is "the marker text at the end of a line", first occurrence, inside the final message only. "Last occurrence anywhere" once cut a real 35 KB answer to 22 KB because the model quoted the marker; "a line of its own" fails because Grok and Gemini glue the marker to the previous sentence, and Gemini can split it across two stream chunks.
- No text is thrown away. Answer after the marker: `ok`. Marker as the last thing in the message: the text before it is kept, reported as `MARKER LAST`. No marker: the whole final message is kept, reported as `NO MARKER`. A failed run's text goes to `partial.md`.
- Completion is judged by structure, never by words in the answer: the launcher's exit result, Grok's `result` event (`is_error`, `subtype`), Gemini's `result` event with `status: success`, DeepSeek's last `step_finish` with `reason: stop`, Codex's last-message file.
- Grok's final text is the assistant text after its last tool call when that carries the marker, otherwise the `result` field (which glues all its messages together).
- A model can finish cleanly and still say "I could not read the files". Only reading the answer catches that.

## Usage and cost

- Codex: `session id:` from stderr, then `token_count` events in `~/.codex/sessions/.../rollout-*<id>*.jsonl`. `input_tokens` there includes cached tokens; the table subtracts them. The plan percentage is the whole weekly window so far, not this poll.
- DeepSeek: sum of `step_finish` events in its own log (`tokens`, `cost`); the cost is opencode's own figure. A missing field makes the column `?`, not 0.
- Grok: `usage` in the final `result` event. Whether `inputTokens` includes cached tokens is not verified.
- Gemini: `stats.models` in the `result` event. `input` = prompt minus cached, `input_tokens` = whole prompt, `output_tokens` = answer only. Reasoning is not reported in this format, so it is taken as total minus prompt minus answer and priced as output. In a `-o json` run the CLI did report it separately and total = prompt + answer + thoughts held exactly; if tool-use prompt tokens are also in the total, the estimate is slightly high.
- Gemini price list in `poll.py` (`GEMINI_PRICES`): Neon $3 input / $15 output per 1M, cached input $0.15, no long-context tier, from https://aistudio.google.com/docs/pricing read 2026-11-20; Hydrogen $1.50 input / $7.50 output per 1M, flat across its context, from published price summaries read 2026-11-18; Carbon and Argon $2 / $10 through 2026-11-30, $4 / $20 from 2026-12-01, from https://aistudio.google.com/learn/gemini-4-carbon-developer-guide; cached input at 5% for all. Not modelled: web-search fees, any long-context tier.

## Reference runs (2026-11-11, about 20-40 KB of files to review)

| Model | Time | Cost |
| --- | --- | --- |
| Codex | 11 and 14 min | plan, about 1% of the weekly window each |
| Grok | 18.5 and 23 min; a third run hung after a lost connection and was stopped at 54 min | plan |
| DeepSeek | 20 min | about $0.15 |
| Gemini (then `gemini-4-carbon`) | 12.5 min | about $0.78 |

## Known traps

- The skill loader replaces dollar-digit tokens in SKILL.md with the invocation arguments (an `awk` program with dollar-zero arrived as the word "Review"). Keep shell and awk out of SKILL.md.
- The app allows six terminal tabs opened by the agent at a time; a seventh `run_in_terminal` is refused until finished tabs are closed.
- `run_in_terminal` wants its working directory inside the session's folders; the launch command does not care which folder it starts in.
- The `sleep` command is blocked in the agent's Bash tool; `poll.py wait` is how it lets time pass (it returns when a model ends or after its time limit).
- Reviewers state guesses as facts. Seen: "the Codex limit window is 5 hours" (it is 7 days), "the API key is visible in the process list" (it was not), "the scratchpad rule does not cover files inside the folder" (it does).
- An exit code of 0 is not success by itself: `agy` once returned 0 with an empty answer.
- An empty Gemini prepayment balance fails fast: on 2026-11-20 a headless run got HTTP 402 `RESOURCE_EXHAUSTED`, "Your prepayment credits are depleted", in under a second, with a `result` event of `status: error` and zero tokens. Seen with the CLI started by hand, not through `poll.py launch`.

## Checks to repeat after a CLI update

1. Gemini read-only: ask it to call `exit_plan_mode`, create a file and run a shell command; none must work, and the copy must stay unchanged. Also confirm the stderr line for a policy that fails to load is still "Policy file error".
2. DeepSeek: ask it to `touch` a file in the home folder and in `/opt/homebrew`, and to `cat` a file in `~/Documents`; all three must fail.
3. Grok: ask it to read a file in `~/Documents` and to create a file in its copy; both must fail, and it must still be signed in. Also start a Grok poll whose topic is 20 characters or longer: it must not end with "EPERM … mkdir '/tmp/.cursor/…'".
4. Codex: the stderr trace must show `sandbox: read-only`, or `workspace-write [workdir, $TMPDIR]` with `--run`.
5. A four-model poll on a tiny project with a failing test and an attached diff: four answers, and the source folder unchanged.
6. Run plain shell commands under the generated `profile.sb` files (see the list above) after changing `sandbox_profile`.
