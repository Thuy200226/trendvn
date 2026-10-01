"""Web settings, read once from the environment (see compose.yaml for where each value comes from)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WebConfig:
    token: str  # bearer token shared with n8n and the browser agent
    data_dir: str
    port: int  # port inside the container
    public_port: str  # port the owner types in the browser (differs from `port` in Docker)
    n8n_port: str
    ui_hosts: frozenset  # Host headers the dashboard answers to
    loopback_hosts: frozenset  # the subset that is "this machine": no password needed
    ui_password: str

    @property
    def ui_origins(self):
        return frozenset({"http://" + h for h in self.ui_hosts} | {"https://" + h for h in self.ui_hosts})

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        token = env.get("TRENDVN_TOKEN", "")
        if len(token) < 32:
            raise RuntimeError("TRENDVN_TOKEN is required")
        public_port = env.get("TRENDVN_PUBLIC_PORT", "5681")
        loopback = frozenset({"localhost:" + public_port, "127.0.0.1:" + public_port, "localhost:8080"})
        extra = {h.strip() for h in env.get("TRENDVN_UI_HOSTS", "").split(",") if h.strip()}  # hosts you deliberately expose
        return cls(
            token=token,
            data_dir=env.get("TRENDVN_DATA", "./data"),
            port=int(env.get("TRENDVN_PORT", "8080")),
            public_port=public_port,
            n8n_port=env.get("TRENDVN_N8N_PORT", "5680"),
            ui_hosts=frozenset(loopback | extra),
            loopback_hosts=loopback,
            ui_password=env.get("TRENDVN_UI_PASSWORD", ""),
        )
