# PR3 gateway envelope rollout

The OCPP processor PR3 requires negotiated-version and connection metadata. For
2.0.1, `Gateway.forward` now publishes an envelope on `<station>/v201/in`, preserving
the original text frame. Legacy versions retain `<station>/in` and raw frames.
Both versions still receive raw OCPP replies on `<station>/out`.

The three-level topic does not match the existing two-level `+/in` IoT rule. A
separate `+/v201/in` rule projects the envelope and derives chargePointId from
topic(1). Existing IoT policy `topic/*/in` covers the additional topic path; no
credential or policy broadening is needed. Each connection receives a new UUID.
OCPP 2.0.1 sends use MQTT QoS 1; processor replay/idempotency handles redelivery.

The deployment preserves the known running ARM64 image at digest
`sha256:a0778481a5ac5b9fe9b9642671b320f50cab8e458ec06c34238e72e19ed5cdbd`.
The Dockerfile adds only gateway.py, without rebuilding dependencies or copying
local certificates. The source and startup files match the inspected deployed
runtime; there are no embedded AWS credential assignments in the new gateway.
Existing repository history and previously committed credentials still require
separate credential rotation/history remediation; rebuilding does not revoke them.

`tools/build_pr3_overlay.py` produces the same single-file overlay through ECR
APIs when Docker is unavailable. It defaults to preparing local artifacts; `--push`
is explicit. It verifies the base manifest/config hashes, preserves ARM64 runtime
configuration, checks source compilation, and records source/image digests. It
never includes the rest of the working directory in the image.

Offline validation: `python -m pytest tests/test_pr3_ingress.py` covers all frame
types, exact text preservation, malformed text forwarding for processor quarantine,
legacy routing and connection identity.

The coordinated infrastructure template lives in the processor repository at
`infrastructure/protocol201-ingress.yaml`. The pre-PR3 processor is preserved as a
version/alias for the old queue. The new queue consumes the PR3 version/alias.
Rollback consists of restoring ECS task definition revision 105; new 2.0.1
connections then resume the old raw route, while already queued v201 messages can
drain through PR3. Do not delete either queue or the transaction journal during
rollback. Physical charger reconnect behavior still requires device testing.

Do not redeploy the entire old CDK stack as part of this cutover: it records task
revision 3 while the service had advanced to revision 105, and its stack-owned
processor mapping is disabled. Reconcile that infrastructure ownership in a
separate change. Registration-only device identity checks are unchanged here;
per-device authentication requires a coordinated provisioning change.
