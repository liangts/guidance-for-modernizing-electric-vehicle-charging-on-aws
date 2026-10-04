# Preserve the verified running ARM64 runtime and dependencies for this rollout.
# Only gateway application code changes; certificates remain runtime-injected.
ARG BASE_IMAGE=920373019462.dkr.ecr.us-east-2.amazonaws.com/cdk-hnb659fds-container-assets-920373019462-us-east-2@sha256:a0778481a5ac5b9fe9b9642671b320f50cab8e458ec06c34238e72e19ed5cdbd
FROM ${BASE_IMAGE}
COPY gateway.py /home/appuser/ocpp-gateway/gateway.py
