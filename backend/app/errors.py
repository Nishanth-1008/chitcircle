class ServiceError(Exception):
    status = 400
    code = "SERVICE_ERROR"

    def __init__(self, detail: str, code: str = None, extra: dict = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        self.extra = extra or {}


class NotFound(ServiceError):
    status, code = 404, "NOT_FOUND"


class Forbidden(ServiceError):
    status, code = 403, "FORBIDDEN"


class Conflict(ServiceError):
    status, code = 409, "CONFLICT"


class Unprocessable(ServiceError):
    status, code = 422, "UNPROCESSABLE"
