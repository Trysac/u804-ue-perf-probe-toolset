"""Fake of the parts of the ``unreal`` module used by the adapter. Not the real engine."""

from __future__ import annotations

from pathlib import Path


class _SystemLibrary:
    def __init__(self, owner):
        self._owner = owner

    def execute_console_command(self, world_context_object, command, specific_player=None):
        self._owner.commands.append(command)


class _Paths:
    def __init__(self, project_dir):
        self._project_dir = project_dir

    def project_dir(self):
        return str(self._project_dir)

    def project_saved_dir(self):
        return str(self._project_dir / "Saved")


class FakeUnreal:
    """Records console commands and drives editor tick callbacks by hand."""

    def __init__(self, project_dir):
        self.project_dir = Path(project_dir)
        self.commands = []
        self.SystemLibrary = _SystemLibrary(self)
        self.Paths = _Paths(self.project_dir)
        self._callbacks = {}
        self._next_handle = 1

    @property
    def csv_dir(self):
        return self.project_dir / "Saved" / "Profiling" / "CSV"

    @property
    def callback_count(self):
        return len(self._callbacks)

    def register_slate_post_tick_callback(self, callback):
        handle = self._next_handle
        self._next_handle += 1
        self._callbacks[handle] = callback
        return handle

    def unregister_slate_post_tick_callback(self, handle):
        self._callbacks.pop(handle, None)

    def tick(self, delta_seconds):
        """Advance the fake editor clock by ``delta_seconds`` without sleeping."""
        for callback in list(self._callbacks.values()):
            callback(delta_seconds)
