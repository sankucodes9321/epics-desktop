class PipelineError(Exception):
    """An operational error whose message is safe to display."""


class SampleRejected(PipelineError):
    """A fresh sample or expiration of lockout may allow the loop to continue."""

    def __init__(self, message, code="sample_rejected"):
        super().__init__(message)
        self.code = code
