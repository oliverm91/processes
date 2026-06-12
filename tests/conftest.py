"""Pytest configuration: ignore the ``manual_tests`` sandbox directory.

Files under ``tests/manual_tests/`` are standalone scripts meant to be run
manually (e.g. ``python tests/manual_tests/manual_email_check.py``) to
inspect logs and outgoing emails.  They are not part of the automated
test suite.
"""

collect_ignore_glob = ["manual_tests/*"]
