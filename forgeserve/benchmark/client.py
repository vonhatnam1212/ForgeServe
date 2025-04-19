# forgeserve/benchmark/client.py
import asyncio
import httpx
import time
import json
import random
from typing import List, Dict, Optional, AsyncGenerator
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from .metrics import RequestResult

class BenchmarkClient:
    """Handles sending concurrent requests and collecting results."""

    def __init__(self,
                 endpoint: str,
                 model_name: str, 
                 prompts: List[str],
                 concurrency: int,
                 max_tokens: int,
                 num_requests: Optional[int] = None,
                 duration_seconds: Optional[int] = None,
                 timeout_seconds: int = 60):
        if not prompts:
            raise ValueError("No prompts provided for benchmarking.")
        if num_requests is None and duration_seconds is None:
            raise ValueError("Either num_requests or duration_seconds must be specified.")
        if num_requests is not None and duration_seconds is not None:
            raise ValueError("Only one of num_requests or duration_seconds can be specified.")

        self.endpoint = endpoint.rstrip('/') + "/v1/completions" 
        self.model_name = model_name
        self.prompts = prompts
        self.concurrency = concurrency
        self.max_tokens = max_tokens
        self.num_requests = num_requests
        self.duration_seconds = duration_seconds
        self.timeout = httpx.Timeout(timeout_seconds)
        self.results: List[RequestResult] = []
        self._start_time = 0.0
        self._stop_event = asyncio.Event()

    async def _make_request(self, client: httpx.AsyncClient, prompt: str, session_results: List[RequestResult], pbar: Optional[Progress] = None, task_id=None):
        """Sends a single request and records the result."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": self.max_tokens,
            "stream": False, 
        }
        start_ts = time.monotonic()
        start_time_abs = time.time()
        output_tokens = None
        success = False
        error_msg = None

        try:
            response = await client.post(self.endpoint, json=payload, timeout=self.timeout)
            end_ts = time.monotonic()
            end_time_abs = time.time()

            if response.status_code == 200:
                try:
                    data = response.json()
                   
                    output_tokens = data.get("usage", {}).get("completion_tokens", 0)
                    success = True
                except json.JSONDecodeError:
                    error_msg = f"Failed to decode JSON response. Status: {response.status_code}"
                except Exception as e:
                    error_msg = f"Error processing response: {e}"
            else:
                 error_msg = f"HTTP Status {response.status_code}: {response.text[:100]}" 

        except httpx.TimeoutException:
            end_ts = time.monotonic()
            end_time_abs = time.time()
            error_msg = "Request timed out"
        except httpx.RequestError as e:
            end_ts = time.monotonic()
            end_time_abs = time.time()
            error_msg = f"Request failed: {e}"
        except Exception as e:
            end_ts = time.monotonic()
            end_time_abs = time.time()
            error_msg = f"Unexpected error: {e}"

        latency = (end_ts - start_ts) * 1000 if success else None 
        result = RequestResult(
            success=success,
            latency_ms=latency,
            output_tokens=output_tokens,
            error=error_msg,
            start_time=start_time_abs,
            end_time=end_time_abs,
        )
        session_results.append(result)
        if pbar and task_id is not None:
            pbar.update(task_id, advance=1, description=f"[{'green' if success else 'red'}]{'OK' if success else 'FAIL'}[/]")

    async def _worker(self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, pbar: Optional[Progress] = None, task_id=None):
        """A worker task that continuously sends requests."""
        session_results = []
        while not self._stop_event.is_set():
            async with semaphore:
                if self._stop_event.is_set(): 
                    break
                prompt = random.choice(self.prompts)
                await self._make_request(client, prompt, session_results, pbar, task_id)
        self.results.extend(session_results)

    async def _run_by_duration(self, client: httpx.AsyncClient, progress: Progress):
        """Runs benchmark for a fixed duration."""
        semaphore = asyncio.Semaphore(self.concurrency)
        task = progress.add_task("[cyan]Running by duration...", total=self.duration_seconds)
        self._start_time = time.monotonic()

        worker_tasks = [
            asyncio.create_task(self._worker(client, semaphore, progress, task))
            for _ in range(self.concurrency)
        ]

        while True:
            elapsed = time.monotonic() - self._start_time
            progress.update(task, completed=min(elapsed, self.duration_seconds), description=f"Running: {elapsed:.1f}s / {self.duration_seconds}s")
            if elapsed >= self.duration_seconds:
                self._stop_event.set() 
                break
            await asyncio.sleep(0.1) 

        progress.update(task, description="[bold blue]Finishing...", completed=self.duration_seconds)
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        progress.update(task, description="[bold green]Duration complete.[/]")


    async def _run_by_requests(self, client: httpx.AsyncClient, progress: Progress):
        """Runs benchmark for a fixed number of requests."""
        semaphore = asyncio.Semaphore(self.concurrency)
        task = progress.add_task("[cyan]Running by requests...", total=self.num_requests)
        self._start_time = time.monotonic()
        session_results = [] 

        req_tasks = []
        for i in range(self.num_requests):
            async def bounded_request(prompt_idx):
                async with semaphore:
                    prompt = self.prompts[prompt_idx % len(self.prompts)]
                    await self._make_request(client, prompt, session_results, progress, task)
            req_tasks.append(bounded_request(i))

        await asyncio.gather(*req_tasks)
        self.results.extend(session_results) 

    async def run(self) -> List[RequestResult]:
        """Runs the benchmark."""
        self.results = [] 
        self._stop_event.clear()

        progress_columns = (
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TextColumn("Reqs: [progress.completed]{task.completed} / [progress.total]{task.total}"),
             TimeElapsedColumn(),
        )

        async with httpx.AsyncClient() as client:
            with Progress(*progress_columns, transient=False) as progress:
                if self.duration_seconds:
                    await self._run_by_duration(client, progress)
                else: 
                    await self._run_by_requests(client, progress)

        return self.results