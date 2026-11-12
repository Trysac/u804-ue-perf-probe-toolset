"""Editor startup: register this plugin's MCP toolset with the Toolset Registry."""

import perf_probe_toolset_mcp
from toolset_registry.registration import Registration

_registration = Registration([perf_probe_toolset_mcp.PerfProbeTools])
_registration.register()
