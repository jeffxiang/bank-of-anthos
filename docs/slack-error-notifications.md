# Slack error notifications

The `frontend`, `userservice`, `contacts` and `ledgerwriter` services can post a
message to a [Slack incoming webhook](https://api.slack.com/messaging/webhooks)
whenever they hit an error path that is otherwise only logged (failed payments
and deposits, failed logins and signups, ledger write failures, ...).

This complements the Prometheus/Alertmanager setup in
[`extras/prometheus`](/extras/prometheus), which only alerts on service
availability (`probe_success == 0`).

## Configuration

| Variable | Description |
| --- | --- |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL. When unset or empty, notifications are disabled. |
| `SLACK_CHANNEL` | Optional channel override, e.g. `#alerts`. Defaults to the webhook's channel. |
| `SLACK_TIMEOUT` | Optional connect/read timeout in seconds for the webhook request (default `3`). |

Notifications are opt-in: with no `SLACK_WEBHOOK_URL` the helper is a no-op, so
local development and tests are unaffected. Slack failures are logged and never
propagated, so a Slack outage cannot change how a request is handled.

## Create the secret

The webhook URL is never hardcoded; the Deployments read it from a Secret named
`app-slack-webhook` (marked `optional`, so the services still start without it):

```sh
kubectl create secret generic app-slack-webhook \
  --from-literal=webhookURL=<YOUR_SLACK_WEBHOOK_URL>
```

To set a channel, add `SLACK_CHANNEL` to the `environment-config` ConfigMap or
to the relevant Deployment's `env` block.
