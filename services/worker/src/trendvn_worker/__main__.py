"""`python -m trendvn_worker` starts the dashboard and API server."""

from .web.server import main

if __name__ == "__main__":
    main()
