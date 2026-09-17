"""Safe errors shared by client network components."""


class Failure(Exception):
    def __init__(self, message: str, needs_login: bool = False):
        super().__init__(message)
        self.needs_login = needs_login
