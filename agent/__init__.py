"""Intentionally does not import agent.agent here.

adk web discovers root_agent directly from agent/agent.py (ADK's
"agents_dir/{name}/agent.py with root_agent defined" pattern -- confirmed via
google.adk.cli.utils.agent_loader source, doesn't require __init__.py to
re-export it). Re-exporting it here previously caused a circular import:
auth/token_broker.py imports agent.config, which -- because Python always
runs a package's __init__.py before any of its submodules -- pulled in
agent.agent -> agent.mcp_config -> auth.token_broker while that module was
still mid-initialization. See docs/troubleshooting.md.
"""
