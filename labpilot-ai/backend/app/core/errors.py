class AppError(Exception):
    """Domain error carrying an HTTP status; converted to a JSON response in main.py."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class NotFound(AppError):
    def __init__(self, detail: str = "Not found"):
        super().__init__(404, detail)


class Forbidden(AppError):
    def __init__(self, detail: str = "You do not have access to this resource"):
        super().__init__(403, detail)


class BadRequest(AppError):
    def __init__(self, detail: str):
        super().__init__(400, detail)
