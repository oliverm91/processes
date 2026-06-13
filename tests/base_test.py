from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from processes import Task


class BaseTest:
    """Base class for all process tests.

    Removes every ``.log`` file from the tests directory before and after
    each test method, so no test depends on prior cleanup and no test
    pollutes the directory for the next one.

    Subclasses should NOT call ``clean_tasks_logs()`` or manually call
    ``os.remove()`` for log files inside ``tests/``.  Override
    ``setup_method`` / ``teardown_method`` (calling ``super()``) to add
    extra fixture logic.
    """

    _CURDIR: ClassVar[str] = os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def _log(cls, filename: str) -> str:
        """Absolute path for a log file inside the tests directory."""
        return os.path.join(cls._CURDIR, filename)

    @classmethod
    def _clean_logs(cls) -> None:
        """Delete every ``.log`` file in the tests directory.

        Silently skips files still locked by an open handler (Windows);
        they will be retried at the next ``setup_method`` call once CPython's
        reference-counting GC has closed the handler.
        """
        for name in os.listdir(cls._CURDIR):
            if name.endswith(".log"):
                try:
                    os.remove(os.path.join(cls._CURDIR, name))
                except PermissionError:
                    pass

    @staticmethod
    def _close_handlers(*tasks: Task) -> None:
        """Close and remove all handlers on each task's logger.

        Necessary on Windows before ``teardown_method`` can delete log files
        that were created by Tasks whose ``Process`` never entered its context
        manager (e.g. when ``Process.__init__`` raises at construction time).
        """
        for t in tasks:
            for h in list(t.logger.handlers):
                h.close()
                t.logger.removeHandler(h)

    def setup_method(self) -> None:
        self._clean_logs()

    def teardown_method(self) -> None:
        self._clean_logs()
