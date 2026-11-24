"""שגיאות עסקיות. הכלים והאגנט מחזירים אותן למודל כטקסט ברור, ה-API כ-400/404."""


class DayPilotError(Exception):
    code = "error"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(DayPilotError):
    code = "not_found"


class ValidationError(DayPilotError):
    code = "invalid"


class StaleProposalError(DayPilotError):
    """הנתונים השתנו מאז שההצעה חושבה. צריך לחשב אותה מחדש."""

    code = "stale_proposal"
