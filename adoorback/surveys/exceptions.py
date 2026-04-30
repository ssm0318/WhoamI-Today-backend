class SurveyNotVisibleError(Exception):
    """Viewer does not pass the BeReal-style result-visibility gate."""

    def __init__(self, *, needs_submission: bool, available_at):
        self.needs_submission = needs_submission
        self.available_at = available_at  # ISO date string or None


class AlreadySubmittedError(Exception):
    pass
