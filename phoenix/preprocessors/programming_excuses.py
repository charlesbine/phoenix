"""Keep a local pool of excuses sampled from programmerexcuses.com."""

import json
import logging
from fcntl import LOCK_EX, LOCK_NB, flock
from html.parser import HTMLParser
from pathlib import Path
from random import choice
from tempfile import TemporaryDirectory
from time import time

import httpx

from phoenix.models import PreprocessorResult
from phoenix.paths import data_path
from phoenix.settings import Settings

# The original site serves its random excuse on HTTP.
SOURCE_URL = "http://programmerexcuses.com/"
REFRESH_SECONDS = 15 * 60
MAX_RESPONSE_BYTES = 32 * 1024
MAX_QUOTE_LENGTH = 256
logger = logging.getLogger(__name__)

QUOTES = [
    "Did you check for a virus on your system?",
    "Don't worry, that value is only wrong half of the time",
    "Even though it doesn't work, how does it feel?",
    "I broke that deliberately to do some testing",
    "I can't test everything",
    "I couldn't find any examples of how that can be done anywhere else in the project",
    "I couldn't find any examples of how that can be done anywhere online",
    "I didn't anticipate that I would make any errors",
    "I didn't receive a ticket for it",
    "I have never seen that before in my life",
    "I have too many other high priority things to do right now",
    "I haven't been able to reproduce that",
    "I haven't had the chance to run that code yet",
    "I haven't touched that code in weeks",
    "I heard there was a solar flare today",
    "I thought I fixed that",
    "I'll have to fix that at a later date",
    "I'm not familiar with it so I didn't fix it in case I made it worse",
    "I'm not getting any error codes",
    "I'm surprised it works as well as it does",
    "It must be a hardware problem",
    "It must be because of a leap second",
    "It probably won't happen again",
    "It was working in my head",
    "It worked yesterday",
    "It works for me",
    "It works, but it's not been tested",
    "It would have taken twice as long to build it properly",
    "It would take too long to rewrite the code from scratch",
    "It's a known bug with the server software",
    "It's a remote vendor issue",
    "It's always been like that",
    "It's an unexpected emergent behaviour of several last minute abstractions",
    "It's just some unlucky coincidence",
    "It's never shown unexpected behaviour like this before",
    "It's not a code problem - our users need more training",
    "Management insisted we wouldn't need to waste our time writing unit tests",
    "Maybe somebody forgot to pay our hosting company",
    "My time was split in a way that meant I couldn't do either project properly",
    "No one told me so I was forced to assume which way to do that",
    "Nobody asked me how long it would actually take",
    "Oh, you said you DIDN'T want that to happen?",
    "Our code quality is no worse than anyone else in the industry",
    "Our internet connection must not be working",
    "THIS can't be the source of THAT",
    "That behaviour is in the original specification",
    "That code was written by the last guy",
    "That feature would be outside of the scope",
    "That important email must have been marked as spam",
    "That's interesting, how did you manage to make it do that?",
    "The accounting department must have cancelled that subscription",
    "The client wanted it changed at the last minute",
    "The code is compiling",
    "The download must have been corrupted",
    "The person responsible doesn't work here anymore",
    "The program has never collected that information",
    "The project manager said no one would want that feature",
    "The request must have dropped some packets",
    "The unit test doesn't cover that eventuality",
    "There must be something strange in your data",
    "There was too little data to bother with the extra functionality at the time",
    "There were too many developers working on that same thing",
    "There's currently a problem with our hosting company",
    "This code was not supposed to go in to production yet",
    "We didn't have enough time to peer review the final changes",
    "We should have updated our software years ago",
    "We spent three months debugging it because we only had one month to build it",
    "Well at least we know not to try that again",
    "What did I tell you about using parts of the system you don't understand?",
    "What did you type in wrong to get it to crash?",
    "Why do you want to do it that way?",
    "You can't use that version on your system",
    "You must have done something wrong",
    "You must have the wrong version",
    "Your browser must be caching the old content",
]


class _ExcuseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] | None = None
        self.quotes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attributes = dict(attrs)
            if attributes.get("href") == "/" and "nofollow" in (attributes.get("rel") or "").split():
                self.parts = []

    def handle_data(self, data: str) -> None:
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.parts is not None:
            quote = " ".join("".join(self.parts).split())
            if 0 < len(quote) <= MAX_QUOTE_LENGTH:
                self.quotes.append(quote)
            self.parts = None


def _fetch_quote() -> str | None:
    try:
        with httpx.stream("GET", SOURCE_URL, timeout=3) as response:
            response.raise_for_status()
            if not response.headers.get("content-type", "").lower().startswith("text/html"):
                return None
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    return None
                body.extend(chunk)
    except httpx.HTTPError as error:
        logger.warning("Programming Excuses refresh failed: %s", error)
        return None

    parser = _ExcuseParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser.quotes[0] if len(parser.quotes) == 1 else None


def _read_pool(path: Path) -> tuple[float, list[str]]:
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return 0, []
    if not isinstance(state, dict):
        return 0, []
    attempted_at = state.get("attempted_at")
    quotes = state.get("quotes")
    return (
        attempted_at if isinstance(attempted_at, (int, float)) else 0,
        [quote for quote in quotes if isinstance(quote, str) and 0 < len(quote) <= MAX_QUOTE_LENGTH]
        if isinstance(quotes, list) else [],
    )


def _write_json(path: Path, value: dict) -> None:
    with TemporaryDirectory(dir=path.parent) as temporary:
        staged = Path(temporary) / path.name
        staged.write_text(json.dumps(value))
        staged.replace(path)


def _pick_quote() -> str:
    pool_path = data_path("programming_excuses_pool")
    with pool_path.with_suffix(".lock").open("a") as lock:
        try:
            # The dashboard preview and renderer share this pool.
            flock(lock, LOCK_EX | LOCK_NB)
        except BlockingIOError:
            _, learned = _read_pool(pool_path)
            return choice(QUOTES + learned)

        attempted_at, learned = _read_pool(pool_path)
        now = time()
        if attempted_at and 0 <= now - attempted_at < REFRESH_SECONDS:
            return choice(QUOTES + learned)

        sample = _fetch_quote()
        is_new = sample is not None and sample not in QUOTES and sample not in learned
        if is_new:
            learned.append(sample)
        _write_json(pool_path, {"attempted_at": now, "quotes": learned})
        return sample if is_new else choice(QUOTES + learned)


def run(settings: Settings) -> PreprocessorResult:
    excuse = _pick_quote()
    _write_json(data_path("programming_excuses"), {"excuse": excuse})
    return PreprocessorResult(data=excuse)
