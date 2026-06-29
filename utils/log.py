import logging
import logging.handlers
from pathlib import Path

from platformdirs import user_log_path
from rich.console import Console
from rich.highlighter import RegexHighlighter
from rich.logging import RichHandler
from rich.markup import escape
from rich.theme import Theme

_APP_NAME = "arso-sprach-zarathustra"


class _VoiceWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "voice will NOT be supported" not in record.getMessage()


class _Formatter(logging.Formatter):
    _with_path = logging.Formatter("%(filename)s:%(lineno)d %(message)s")
    _plain = logging.Formatter("%(message)s")

    def format(self, record: logging.LogRecord) -> str:
        fmt = self._with_path if record.levelno >= logging.ERROR else self._plain
        return fmt.format(record)


class _DiscordHighlighter(RegexHighlighter):
    """Highlights patterns in discord.py's own log messages that we can't mark up ourselves."""

    base_style = "bot."
    highlights = [r"(?P<id>[0-9a-f]{32,})"]


# All color decisions live here. Only standard ANSI colors — no RGB values.
THEME = Theme(
    {
        "bot.name": "bold",
        "bot.id": "dim",
        "bot.command": "bold cyan",
        "bot.timing": "dim",
        "bot.cron": "magenta",
        "bot.count": "yellow",
        "bot.ok": "green",
        "bot.fail": "red",
    }
)


def _file_handler() -> logging.handlers.RotatingFileHandler:
    log_dir: Path = user_log_path(_APP_NAME)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(filename)s:%(lineno)d %(message)s")
    )
    handler.addFilter(_VoiceWarningFilter())
    return handler


def setup_logging(level: int = logging.INFO) -> None:
    console = Console(theme=THEME, stderr=True)
    rich_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
        highlighter=_DiscordHighlighter(),
        console=console,
    )
    rich_handler.addFilter(_VoiceWarningFilter())
    rich_handler.setFormatter(_Formatter())
    logging.basicConfig(
        level=level,
        datefmt="[%X]",
        handlers=[rich_handler, _file_handler()],
    )
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def fmt_id(entity_id: int | str) -> str:
    return f"[bot.id]#{entity_id}[/bot.id]"


def fmt_cmd(name: str) -> str:
    return f"[bot.command]/{name}[/bot.command]"


def fmt_timing(seconds: str) -> str:
    return f"[bot.timing]({seconds}s)[/bot.timing]"


def fmt_entity(name: str, entity_id: int | str) -> str:
    return f"[bot.name]{escape(name)}[/bot.name]{fmt_id(entity_id)}"
