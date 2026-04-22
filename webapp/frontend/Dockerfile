# =============================================================================
# Frontend — Vite dev server
#
# Build context: webapp/frontend/
#
# For Phase 1 we run the Vite development server inside the container so
# Hot Module Replacement works during active development.  A production-
# optimised multi-stage build (node build → nginx static serve) is deferred
# to Phase 5 hardening.
# =============================================================================
FROM node:20-alpine

# Prevent npm from writing audit warnings and fund notices to stdout, which
# would clutter Docker build output.
ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false

WORKDIR /app

# Install dependencies in a separate layer so subsequent code changes do
# not trigger a full re-install.
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the source tree.
COPY . .

EXPOSE 5173

# --host 0.0.0.0 makes the dev server reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
