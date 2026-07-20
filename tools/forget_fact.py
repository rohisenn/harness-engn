from agent.memory import forget_fact as _forget_fact

def forget_fact(fact: str) -> str:
    """
    Removes a persistent fact from memory, if it matches any part of the saved fact.
    """
    return _forget_fact(fact)
