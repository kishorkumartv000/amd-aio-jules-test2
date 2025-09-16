import asyncio
from bot.helpers.message import edit_message
from bot.helpers.interval import SetInterval

# Dictionary to hold the active status updater intervals for each task.
# The key will be a unique task ID, and the value will be the SetInterval instance.
STATUS_UPDATERS = {}
# A lock to safely access the STATUS_UPDATERS dictionary
STATUS_LOCK = asyncio.Lock()

async def update_status_message(task_id: str, reporter, message):
    """
    The core function for the periodic status update.
    Renders the reporter's state and edits the message.
    """
    if not reporter or not message:
        return

    try:
        text = await reporter.render()
        # Only edit the message if the text has actually changed.
        if message.text != text:
            await edit_message(message, text)
            # This is a bit of a hack to update the in-memory message object
            # so we can check against it next time.
            message.text = text
    except Exception as e:
        from bot.logger import LOGGER
        LOGGER.error(f"Error updating status for task {task_id}: {e}")


async def start_status_updater(task_id: str, reporter, message, interval: int = 5):
    """Starts a new periodic status updater for a given task."""
    async with STATUS_LOCK:
        # If there's an existing updater for this task, cancel it first.
        if task_id in STATUS_UPDATERS:
            STATUS_UPDATERS[task_id].cancel()

        # Create and start the new interval.
        interval_job = SetInterval(interval, update_status_message, task_id, reporter, message)
        interval_job.start()
        STATUS_UPDATERS[task_id] = interval_job


async def stop_status_updater(task_id: str):
    """Stops the periodic status updater for a given task."""
    async with STATUS_LOCK:
        if task_id in STATUS_UPDATERS:
            STATUS_UPDATERS[task_id].cancel()
            del STATUS_UPDATERS[task_id]
