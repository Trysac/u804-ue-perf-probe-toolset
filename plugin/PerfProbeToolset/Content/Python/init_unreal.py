"""Editor startup: register this plugin's MCP toolset with the Toolset Registry (same pattern as Epic's toolsets)."""

from toolset_registry.registration import Registration

import perf_probe_toolset_mcp

_registration = Registration([perf_probe_toolset_mcp.PerfProbeTools])
_registration.register()
