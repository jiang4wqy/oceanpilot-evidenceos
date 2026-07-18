class SensitiveDataRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("sensitive data is not accepted")


class InvalidTransition(Exception):
    """A case command is not allowed in the current state."""

    def __init__(self) -> None:
        super().__init__("case command is not allowed in the current state")
