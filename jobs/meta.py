from lib.jobs.registry import job_registry


class JobMeta(type):
    """
    Auto registers every concrete BaseJob subclass into the job registry.
    """

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if bases:
            job_registry.register(cls)

        return cls
