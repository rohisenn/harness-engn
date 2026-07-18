# harness

An open-source coding agent, built up one milestone at a time.

`harness` understands a repository, plans an approach, edits files, runs
commands, fixes errors, and iterates until a task is done:

```bash
harness "Add JWT authentication"
harness "Fix failing tests"
```

This repo is being built incrementally and in the open. Each milestone
below is a fully working system in itself, not a stub.

## Status

- [x] **Milestone 1** — CLI that talks to an LLM
- [x] Milestone 2 — Read files
- [x] Milestone 3 — Edit files
- [x] Milestone 4 — Execute terminal commands
- [x] Milestone 5 — Repository search
- [ ] Milestone 6 — Planning
- [ ] Milestone 7 — Memory
- [ ] Milestone 8 — Self-correction loop
- [ ] Milestone 9 — Git integration
- [ ] Milestone 10 — Multi-agent collaboration

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and add your ANTHROPIC_API_KEY or OPENAI_API_KEY
```

## Usage

```bash
# one-shot
python main.py "Explain what this repo does"

# interactive
python main.py

# override provider/model for a single run
python main.py "Fix the bug in parser.py" --provider openai --model gpt-4o
```

## Architecture (so far)

```
harness/
├── agent/
│   ├── config.py      # loads .env once, exposes a typed Config object
│   ├── llm.py          # provider-agnostic streaming LLM client
│   └── prompts.py      # system prompt(s)
├── tools/               # filesystem/terminal command execution tools
├── tests/
├── main.py              # CLI entrypoint (click + rich)
├── requirements.txt
└── .env.example
```

Design principles carried through every milestone:

1. **Provider-agnostic core.** `agent/llm.py` is the only file that knows
   about the Anthropic/OpenAI SDKs. Everything else talks to `LLMClient`.
2. **Config in one place.** `agent/config.py` reads environment variables
   once; nothing else touches `os.environ` directly.
3. **Tools are isolated.** As we add file editing, terminal execution, and
   search, each lives in its own module under `tools/` with a narrow,
   testable interface, so the agent loop can call them uniformly.

## Roadmap: what's coming

- Repository indexing & semantic code search
- Context compression (so large repos don't blow the context window)
- Automatic test execution + error recovery loop
- Multi-file editing
- Git commits & PR generation
- Model switching, local model support
- MCP support, plugin system
- Interactive terminal UI

## Why this exists

This project is a from-scratch exploration of the engineering behind
modern coding agents — planning, tool use, memory, self-correction — not
a clone of any particular product. Each milestone is meant to be readable
and understandable end to end.
