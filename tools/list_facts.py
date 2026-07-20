from agent.memory import load_facts

def list_facts() -> str:
    """
    Lists all persistent facts currently remembered about the repository.
    """
    facts = load_facts()
    if not facts:
        return "No facts remembered yet."
    return "Repository Facts/Memory:\n" + "\n".join(f"- {f}" for f in facts)
