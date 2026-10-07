# nightcall box: Claude Code + Codex + python3 + git, a non-root user, and the egress firewall.
# Built by scripts/box.sh on the first `night-loop.sh --box` when Docker is up.
FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 git tzdata ca-certificates curl iptables ipset dnsutils util-linux procps \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code @openai/codex && npm cache clean --force
COPY claude /opt/box/bin/claude
COPY firewall.sh /opt/box/firewall.sh
ENV PATH=/opt/box/bin:$PATH DISABLE_AUTOUPDATER=1 NIGHTCALL_IN_BOX=1 \
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=*
ENTRYPOINT ["/opt/box/firewall.sh"]
