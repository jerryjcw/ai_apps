"""FastAPI web application for Scholar Inbox Curate.

Provides a web UI for dashboard, paper list, and manual ingestion triggers.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.config import AppConfig
from src.db import get_connection


def create_app(config: AppConfig) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    config : AppConfig
        Application configuration

    Returns
    -------
    FastAPI
        Configured FastAPI application
    """
    app = FastAPI(
        title="Scholar Inbox Curate",
        description="Monitor Scholar Inbox paper recommendations and track citation traction",
        version="0.1.0",
    )

    # Store config in app state for use in routes
    app.state.config = config
    app.state.db_path = config.db_path

    # Health check endpoint
    @app.get("/health")
    async def health():
        """Health check endpoint for monitoring.

        Verifies database connectivity and returns basic status information.

        Returns
        -------
        dict
            Status object with status and optional detail fields
        """
        try:
            with get_connection(config.db_path) as conn:
                conn.execute("SELECT 1")
            return {"status": "ok", "service": "scholar-inbox-curate"}
        except Exception as e:
            return (
                JSONResponse(
                    status_code=503,
                    content={"status": "error", "detail": str(e)},
                )
            )

    @app.get("/api/stats")
    async def get_stats():
        """Get dashboard statistics.

        Returns
        -------
        dict
            Dashboard statistics including paper counts, trending papers, etc.
        """
        from src.db import get_dashboard_statistics

        try:
            with get_connection(config.db_path) as conn:
                stats = get_dashboard_statistics(conn)
            return stats
        except Exception as e:
            return (
                JSONResponse(
                    status_code=500,
                    content={"error": str(e)},
                )
            )

    @app.get("/api/trending")
    async def get_trending(limit: int = 10):
        """Get trending papers by citation velocity.

        Parameters
        ----------
        limit : int
            Maximum number of papers to return (default: 10)

        Returns
        -------
        list[dict]
            Trending papers ordered by citation velocity
        """
        from src.db import get_trending_papers

        try:
            with get_connection(config.db_path) as conn:
                papers = get_trending_papers(conn, limit=limit)
            return papers
        except Exception as e:
            return (
                JSONResponse(
                    status_code=500,
                    content={"error": str(e)},
                )
            )

    @app.post("/partials/trigger-rules")
    async def trigger_rules():
        """Trigger prune/promote rules and return a status summary.

        Returns
        -------
        dict
            Summary with papers_evaluated, papers_pruned, papers_promoted.
        """
        from src.db import now_utc
        from src.rules import run_prune_promote

        try:
            with get_connection(config.db_path) as conn:
                now = now_utc()
                result = run_prune_promote(conn, config, now)
            return {
                "status": "completed",
                "papers_evaluated": result.papers_evaluated,
                "papers_pruned": result.papers_pruned,
                "papers_promoted": result.papers_promoted,
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "detail": str(e)},
            )

    return app
