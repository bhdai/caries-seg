# ==============================================================================
# Makefile — carries-seg
# ==============================================================================
#
# Machine-specific config (SERVER_USER, SERVER_HOST, REMOTE_PATH) lives in
# Makefile.local, which is gitignored. Copy Makefile.local.example to get
# started:
#
#   cp Makefile.local.example Makefile.local
#
# Then edit Makefile.local with your server details.

-include Makefile.local

# Fail early with a clear message if the required vars are not set.
_check-server-vars:
	@if [ -z "$(SERVER_USER)" ] || [ -z "$(SERVER_HOST)" ] || [ -z "$(REMOTE_PATH)" ]; then \
		echo ""; \
		echo "  ERROR: SERVER_USER, SERVER_HOST, and REMOTE_PATH must be set."; \
		echo "  Copy Makefile.local.example → Makefile.local and fill in your values."; \
		echo ""; \
		exit 1; \
	fi

# ------------------------------------------------------------------------------
# sync — push project files to the server
# ------------------------------------------------------------------------------
#
# Uses --checksum so only genuinely changed files are transferred (avoids
# timestamp-only false positives common on network filesystems).
# --delete removes files on the remote that no longer exist locally, keeping
# the remote a clean mirror of what's in the repo.

.PHONY: sync
sync: _check-server-vars
	rsync -avz --checksum \
		--exclude-from=.rsyncignore \
		./ $(SERVER_USER)@$(SERVER_HOST):$(REMOTE_PATH)/

# ------------------------------------------------------------------------------
# sync-dry — preview what would change without actually transferring
# ------------------------------------------------------------------------------

.PHONY: sync-dry
sync-dry: _check-server-vars
	rsync -avzn --checksum \
		--exclude-from=.rsyncignore \
		./ $(SERVER_USER)@$(SERVER_HOST):$(REMOTE_PATH)/

# ------------------------------------------------------------------------------
# ssh — open a shell on the server
# ------------------------------------------------------------------------------

.PHONY: ssh
ssh: _check-server-vars
	ssh $(SERVER_USER)@$(SERVER_HOST)
