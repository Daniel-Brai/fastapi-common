from lib.jobs.schedule import CronSchedule, IntervalSchedule, OnceAt

type JobSchedule = CronSchedule | IntervalSchedule | OnceAt
