"""
telethon_manager/main.py — головний сервіс для Telethon-акаунтів.
"""
import asyncio
import logging
import os
import signal
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("telethon_manager")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
TELETHON_API_KEY = os.getenv("TELETHON_API_KEY", "")
POLL_INTERVAL = 30  # секунд

from account_worker import AccountWorker
from history_loader import load_group_history


class TelethonManager:
    def __init__(self):
        self.workers: dict[str, AccountWorker] = {}
        self.history_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._shutdown = False

    async def fetch_accounts(self) -> list:
        """Отримати список активних акаунтів з backend."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{BACKEND_URL}/api/tg-accounts/internal",
                    headers={"X-Api-Key": TELETHON_API_KEY},
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.error(f"Failed to fetch accounts: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Failed to fetch accounts: {e}")
        return []

    async def fetch_account_groups(self, account_id: str) -> list:
        """Отримати список груп для акаунту."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{BACKEND_URL}/api/tg-accounts/{account_id}/groups/internal",
                    headers={"X-Api-Key": TELETHON_API_KEY},
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.error(f"Failed to fetch groups for {account_id}: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Failed to fetch groups for {account_id}: {e}")
        return []

    async def start_worker(self, account: dict, groups: list):
        """Підготувати акаунт: спочатку історія, потім live."""
        account_id = account["id"]
        if account_id in self.workers:
            return
        if not account.get("session_string"):
            logger.warning(f"Account {account['phone']} has no session_string, skipping")
            return

        worker = AccountWorker(account, groups)
        self.workers[account_id] = worker
        try:
            await worker.connect()
            await self._load_pending_history(account_id, worker, groups)
            worker.update_groups(groups)
            await worker.start_live()
            logger.info(f"Started live worker for {account['phone']}")
        except Exception:
            await worker.stop()
            self.workers.pop(account_id, None)
            raise

    async def _run_history_loader(self, client, account_id: str, group: dict):
        """Запустити завантаження історії в окремій задачі."""
        task_key = (account_id, group["group_id"])
        try:
            tg_group = await client.get_entity(int(group["telegram_id"]))
            await load_group_history(
                client,
                account_id,
                group["group_id"],
                tg_group,
                last_message_id=group.get("last_message_id"),
            )
        except Exception as e:
            logger.error(f"History loader error for group {group['group_id']}: {e}")
        finally:
            self.history_tasks.pop(task_key, None)

    def _eligible_group(self, group: dict) -> bool:
        telegram_id = group.get("telegram_id")
        return (
            group.get("is_active")
            and telegram_id is not None
            and int(telegram_id) < 0
        )

    async def _load_pending_history(self, account_id: str, worker: AccountWorker, groups: list):
        pending_groups = [
            group
            for group in groups
            if self._eligible_group(group) and not group.get("history_loaded")
        ]
        pending_groups.sort(key=lambda group: int(group["telegram_id"]))

        for group in pending_groups:
            task_key = (account_id, group["group_id"])
            if task_key in self.history_tasks and not self.history_tasks[task_key].done():
                await self.history_tasks[task_key]
                continue

            task = asyncio.create_task(
                self._run_history_loader(worker.client, account_id, group)
            )
            self.history_tasks[task_key] = task
            await task

    async def sync(self):
        """Синхронізувати список акаунтів і груп."""
        accounts = await self.fetch_accounts()
        active_ids = set()

        for account in accounts:
            if not account.get("is_active") or account.get("status") != "active":
                continue
            account_id = account["id"]
            active_ids.add(account_id)
            groups = await self.fetch_account_groups(account_id)

            if account_id not in self.workers:
                await self.start_worker(account, groups)
            else:
                worker = self.workers[account_id]
                worker.account = account
                await worker.connect()
                await self._load_pending_history(account_id, worker, groups)
                worker.update_groups(groups)

        # Зупинити воркери для деактивованих акаунтів
        for account_id in list(self.workers.keys()):
            if account_id not in active_ids:
                logger.info(f"Stopping worker for {account_id}")
                for task_key, task in list(self.history_tasks.items()):
                    if task_key[0] == account_id:
                        task.cancel()
                        self.history_tasks.pop(task_key, None)
                await self.workers[account_id].stop()
                del self.workers[account_id]

    async def run(self):
        logger.info("TelethonManager starting...")
        # Чекаємо поки backend запуститься
        for attempt in range(30):
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(f"{BACKEND_URL}/")
                    if r.status_code == 200:
                        break
            except Exception:
                pass
            logger.info(f"Waiting for backend... ({attempt+1}/30)")
            await asyncio.sleep(5)

        await self.sync()

        while not self._shutdown:
            await asyncio.sleep(POLL_INTERVAL)
            await self.sync()

    async def shutdown(self):
        self._shutdown = True
        for task in self.history_tasks.values():
            task.cancel()
        self.history_tasks.clear()
        for worker in self.workers.values():
            await worker.stop()
        logger.info("TelethonManager stopped.")


async def main():
    manager = TelethonManager()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(manager.shutdown()))

    await manager.run()


if __name__ == "__main__":
    asyncio.run(main())
