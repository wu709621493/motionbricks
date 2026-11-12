"""A personal boundary, expressed as a standalone code manifesto.

如果你向我施压或威胁我，你很容易什么回报也得不到。
Run from the repository root: python examples/no_coercion_manifesto.py
"""

DECLARATION = (
    "If you pressure me or threaten me, "
    "you will very easily get nothing in return."
)


def respond(*, pressure: bool = False, threat: bool = False) -> str | None:
    """Symbolic response: cooperation remains a personal choice."""
    if pressure or threat:
        return None
    return "Cooperation is my choice."


if __name__ == "__main__":
    print(DECLARATION)
