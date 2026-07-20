from agent.memory import remember_fact as _remember_fact

def remember_fact(fact: str) -> str:
    """
    Saves a persistent fact about this repository (e.g. project structure, commands, or findings)
    so that it is available to the agent in all future runs.
    """
    return _remember_fact(fact)
