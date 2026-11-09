# claude-skills

Personal Claude Code skills.

- `multi-model-review/` — poll Codex, DeepSeek, Gemini and Grok independently for architecture
  decisions, spec/plan/code review and hard bugs, then check their claims against the source.

Install: clone this repo and link a skill folder into `~/.claude/skills/`, e.g.

```bash
ln -s "$PWD/multi-model-review" ~/.claude/skills/multi-model-review
```
