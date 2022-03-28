from __future__ import annotations

import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from apscheduler.job import Job as APJob

    from ..poll.workflow import PollWorkflow
    from ..server.session.session import UserSession

logger = logging.getLogger(__name__)


class Job:
    def __init__(self, scheduler: AsyncIOScheduler, job_queue: asyncio.Queue, id: str = None) -> None:
        self._scheduler = scheduler
        self._job_queue = job_queue
        self._id = id
        self._apjob: APJob | None = None

        if id:
            self._apjob = scheduler.get_job(id)

    @property
    def id(self) -> str | None:
        return self._id

    def schedule(self, trigger: BaseTrigger):
        self._schedule(trigger=trigger)

    def _schedule(self, trigger: BaseTrigger, name: str = None):
        self._apjob = self._scheduler.add_job(
            func=self._callback,
            trigger=trigger,
            args=self,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=10,
            name=name,
        )
        self._id = self._apjob.id

    async def _callback(self):
        await self._job_queue.put(self)

    def remove(self) -> None:
        """Remove all jobs matching this job key from queue"""

        self._apjob.remove()

    def run_once(self, when: datetime.datetime | datetime.time):
        if isinstance(when, datetime.time):
            when = datetime.datetime.now().replace(
                hour=when.hour, minute=when.minute, second=when.second, microsecond=when.microsecond, tzinfo=when.tzinfo
            )

        self.schedule(DateTrigger(run_date=when))

    def run_daily(
        self,
        time: datetime.time,
        days: Tuple[int, ...] = tuple(range(7)),
    ):
        self.schedule(
            CronTrigger(
                day_of_week=",".join([str(d) for d in days]),
                hour=time.hour,
                minute=time.minute,
                second=time.second,
                timezone=time.tzinfo,
            )
        )


class UserJob(Job):
    """Context used for jobs related to a single chat"""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        job_queue: asyncio.Queue,
        user_session: UserSession,
        job_name: str = "undefined",
        id: str = None,
    ) -> None:
        super().__init__(scheduler=scheduler, job_queue=job_queue, id=id)
        self._user_session = user_session
        self._job_name = job_name
        self._user_session.jobs[self.job_key] = self

    @property
    def job_key(self) -> str:
        return str(self.user_id) + "_" + self._job_name

    @property
    def user_session(self) -> UserSession:
        return self._user_session

    # Convenience propoerties
    @property
    def user_id(self) -> str:
        return self._user_session.user_id

    def schedule(self, trigger: BaseTrigger):
        self._schedule(trigger=trigger, name=self.job_key)

    def remove(self) -> None:
        """Removes job from scheduler and from user_session."""

        job_key = self.job_key

        super().remove()

        if job_key in self._user_session.jobs:
            del self._user_session.jobs[job_key]


class NewPollJob(UserJob):
    """Special job used for initiating a new poll"""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        job_queue: asyncio.Queue,
        user_session: UserSession,
        poll_name: str,
        job_name: str = "undefined",
        id: str = None,
    ) -> None:
        super().__init__(scheduler=scheduler, job_queue=job_queue, user_session=user_session, job_name=job_name, id=id)

        self._poll_name = poll_name

    @property
    def poll_name(self) -> str:
        return self._poll_name

    @property
    def poll_workflow(self) -> PollWorkflow:
        return self._user_session.active_polls[self._poll_name]


class ActivePollJob(NewPollJob):
    """Special job used for jobs within an active poll (e.g. delays)"""

    pass
