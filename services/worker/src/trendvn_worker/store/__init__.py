"""SQLite persistence. `Store` is the one object the rest of the worker talks to; each concern lives in its own module."""

from .accounts import AccountsMixin
from .base import StoreBase
from .captions import CaptionMixin
from .channels import ChannelsMixin
from .chat import ChatMixin
from .commission import CommissionMixin
from .feedback import FeedbackMixin
from .health import HealthMixin
from .ingest import IngestMixin
from .publishing import PublishingMixin
from .post_deletions import PostDeletionsMixin
from .queue import QueueMixin
from .reporting import ReportingMixin
from .retention import RetentionMixin
from .task_log import TaskLogMixin
from .videos import VideosMixin


class Store(
    StoreBase,
    AccountsMixin,
    IngestMixin,
    QueueMixin,
    HealthMixin,
    PublishingMixin,
    PostDeletionsMixin,
    CaptionMixin,
    TaskLogMixin,
    FeedbackMixin,
    ReportingMixin,
    RetentionMixin,
    ChatMixin,
    ChannelsMixin,
    VideosMixin,
    CommissionMixin,
):
    """The whole database API (ingest, queue, publishing, captions, tasks, feedback, reporting)."""
