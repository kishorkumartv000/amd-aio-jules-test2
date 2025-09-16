import asyncio
import time

class SetInterval:
    def __init__(self, interval, func, *args, **kwargs):
        self._interval = interval
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._task = None
        self._is_running = False

    async def _run(self):
        self._is_running = True
        while self._is_running:
            start_time = time.monotonic()
            try:
                await self._func(*self._args, **self._kwargs)
            except Exception as e:
                # Log errors from the wrapped function
                from bot.logger import LOGGER
                LOGGER.error(f"Error in SetInterval task: {e}", exc_info=True)

            elapsed = time.monotonic() - start_time
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    def start(self):
        if not self._is_running:
            self._task = asyncio.create_task(self._run())

    def cancel(self):
        if self._is_running:
            self._is_running = False
            if self._task:
                self._task.cancel()
                self._task = None
