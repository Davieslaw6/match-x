import asyncio, random, time
from datetime import date
import httpx

class QuotaExhausted(Exception): ...
class CircuitOpen(Exception): ...
class ProviderError(Exception): ...

class QuotaBudget:
    def __init__(self, daily: int): self.daily, self.used, self.day = daily, 0, date.today()
    def take(self):
        if self.day != date.today(): self.day, self.used = date.today(), 0
        if self.used >= self.daily: raise QuotaExhausted("daily provider budget exhausted")
        self.used += 1

class CircuitBreaker:
    def __init__(self, threshold=3, reset_s=60, clock=time.monotonic):
        self.threshold, self.reset_s, self.clock, self.fails, self.opened = threshold, reset_s, clock, 0, None
    def check(self):
        if self.opened is not None:
            if self.clock() - self.opened < self.reset_s: raise CircuitOpen("circuit open")
            self.opened, self.fails = None, 0  # half-open: allow one try
    def ok(self): self.fails, self.opened = 0, None
    def fail(self):
        self.fails += 1
        if self.fails >= self.threshold: self.opened = self.clock()

async def get_json(client: httpx.AsyncClient, url, *, budget: QuotaBudget, breaker: CircuitBreaker,
                   retries=3, base=0.5, sleep=asyncio.sleep, **kw):
    breaker.check()
    for attempt in range(retries + 1):
        budget.take()
        try:
            r = await client.get(url, timeout=10, **kw)
        except httpx.TransportError:
            r = None
        if r is not None and r.status_code < 400:
            breaker.ok(); return r.json()
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            raise ProviderError(f"HTTP {r.status_code}")  # client error: do not retry
        if attempt == retries: break
        delay = base * 2 ** attempt * random.uniform(0.5, 1.5)
        if r is not None and r.status_code == 429 and r.headers.get("retry-after", "").isdigit():
            delay = max(delay, float(r.headers["retry-after"]))
        await sleep(delay)
    breaker.fail(); raise ProviderError("provider unavailable after retries")
