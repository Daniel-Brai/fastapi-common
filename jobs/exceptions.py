class JobError(Exception):
    """
    Base class for exceptions for all jobs
    """

    def __init__(self, message: str = "An error occurred while processing the job"):
        self.type = "job_error"
        self.message = message
        super().__init__(message)


class JobNotFoundError(JobError):
    def __init__(self, message: str = "The specified job was not found"):
        super().__init__(message)


class JobConfigurationError(RuntimeError):
    def __init__(self, message: str = "Invalid job configuration"):
        super().__init__(message)


class InvalidJobScheduleError(JobError):
    def __init__(self, message: str = "Invalid job schedule provided"):
        super().__init__(message)
