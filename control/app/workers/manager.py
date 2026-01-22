"""Worker manager for running multiple job workers."""
import asyncio
import logging
import signal
from typing import Optional

from app.config import get_settings
from app.workers.job_worker import JobWorker

settings = get_settings()
logger = logging.getLogger(__name__)


class WorkerManager:
    """
    Manages a pool of job workers.

    Handles startup, shutdown, and signal handling for graceful termination.
    """

    def __init__(self, worker_count: Optional[int] = None) -> None:
        self.worker_count = worker_count or settings.job_worker_count
        self.workers: list[JobWorker] = []
        self.tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start all workers."""
        logger.info(f"Starting {self.worker_count} job workers")

        # Create and start workers
        for i in range(self.worker_count):
            worker = JobWorker(worker_id=f"worker-{i}")
            self.workers.append(worker)
            task = asyncio.create_task(worker.start())
            self.tasks.append(task)

        logger.info(f"Started {len(self.workers)} workers")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Stop all workers
        await self.stop()

    async def stop(self) -> None:
        """Stop all workers gracefully."""
        logger.info("Stopping all workers...")

        # Signal all workers to stop
        for worker in self.workers:
            await worker.stop()

        # Wait for tasks to complete with timeout
        if self.tasks:
            done, pending = await asyncio.wait(
                self.tasks,
                timeout=30.0,
                return_when=asyncio.ALL_COMPLETED,
            )

            # Cancel any remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("All workers stopped")

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._shutdown_event.set()

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.request_shutdown)


async def run_workers(worker_count: Optional[int] = None) -> None:
    """Main entry point for running workers."""
    manager = WorkerManager(worker_count)

    # Setup signal handlers (Unix only)
    try:
        manager.setup_signal_handlers()
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        pass

    await manager.start()


def main() -> None:
    """CLI entry point for running workers."""
    import argparse

    parser = argparse.ArgumentParser(description="Run WalStream job workers")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Number of workers (default: {settings.job_worker_count})",
    )
    args = parser.parse_args()

    asyncio.run(run_workers(args.workers))


if __name__ == "__main__":
    main()
