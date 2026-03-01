FROM grafana/grafana:10.3.1

# Copy the built custom plugin into the Grafana plugins directory
COPY llm-platform-ops/dist/ /var/lib/grafana/plugins/llmplatform-ops-panel/

# Allow loading our unsigned custom plugin
ENV GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=llmplatform-ops-panel
