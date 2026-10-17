# Runs the MCP server itself (stdio transport) — this image does not bundle
# PHP/Composer, so the subprocess-based checks (module_risk's phpcs/phpstan/
# rector, security_audit, outdated_packages) report scanned=false with a
# reason when run from inside this container. See README.md's
# "Projects that develop inside Docker/DDEV/Warden/Lando" section for
# MCP_MAGENTO_AUDIT_EXEC_PREFIX, which exists for exactly this situation.
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["mcp-magento-audit"]
