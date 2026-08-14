from __future__ import annotations

from collections.abc import Callable

from .actions import system_info, system_ping
from .config import RunnerConfig
from .files import files_list_directory, files_search
from .programs import program_list, program_run
from .system_status import system_status


ActionHandler = Callable[[dict, RunnerConfig], dict]
_REGISTRY: dict[str, ActionHandler] = {
    "system.ping": lambda arguments, config: _empty_arguments(arguments, system_ping, config),
    "system.info": lambda arguments, config: _empty_arguments(arguments, system_info, config),
    "system.status": lambda arguments, config: _empty_arguments(arguments, system_status, config),
    "files.list_directory": files_list_directory,
    "files.search": files_search,
    "program.list": program_list,
    "program.run": program_run,
}


def _empty_arguments(arguments: dict, handler: Callable[[RunnerConfig], dict], config: RunnerConfig) -> dict:
    if arguments:
        raise ValueError("this action accepts no arguments")
    return handler(config)


def registered_actions() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def get_action(action: str) -> ActionHandler | None:
    return _REGISTRY.get(action)
