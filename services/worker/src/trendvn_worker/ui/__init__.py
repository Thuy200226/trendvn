"""The dashboard: server-rendered HTML (no external assets, every dynamic value escaped). Pages are built from per-tab modules."""

from .components import task_panel
from .format import ago, num
from .labels import vi_reason
from .login import login_page
from .page import render
from .tabs.search import chat_thread

__all__ = ["render", "chat_thread", "task_panel", "login_page", "vi_reason", "ago", "num"]
