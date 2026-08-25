---
name: testing-bank-of-anthos-uis
description: How to run and browser-test the Bank of Anthos frontends (Flask src/frontend and the Angular src/ui-angular SPA) on a local minikube cluster, including parity testing between them.
---

# Testing the Bank of Anthos frontends locally

## Bringing the stack up
- The app runs on minikube with the manifests in `kubernetes-manifests/` (8 original pods) plus `ui-angular` if that frontend exists.
- Off-GCP, tracing/metrics exporters crash the Java/Python services. Disable them before expecting pods to become Ready:
  `kubectl set env deployment --all ENABLE_TRACING=false ENABLE_METRICS=false`
- Expose the UIs with port-forwards (each in its own background shell):
  - Flask UI: `kubectl port-forward svc/frontend 8080:80` → http://127.0.0.1:8080
  - Angular UI: `kubectl port-forward svc/ui-angular 8081:80` → http://127.0.0.1:8081
- Rebuild the Angular image after a fix:
  `cd src/ui-angular && eval "$(minikube docker-env)" && docker build -t ui-angular:latest . && kubectl rollout restart deployment/ui-angular`

## Credentials and runtime config
- Demo login: `testuser` / `bankofanthos` (seeded demo account `1011226111`).
- `LOCAL_ROUTING_NUM` is `883745000` in the default `environment-config` ConfigMap; the deposit form must reject an external routing number equal to it.
- The Angular SPA reads demo creds and local routing from `GET /config.json`, rendered by nginx from env vars. Sanity check it first:
  `curl -s http://127.0.0.1:8081/config.json`
  Expect `{"demoUsername":"...","demoPassword":"...","localRouting":"..."}`. If it returns the literal `${VAR}` placeholders, the ConfigMap wiring in the deployment is broken.
- Angular stores its JWT in `sessionStorage.token`; Flask uses a `token` cookie. They are independent sessions, so you can drive both UIs side by side in two tabs of the same browser.

## Parity testing tips
- Treat `src/frontend/frontend.py` and `src/frontend/templates/*` as the spec. Useful anchors: `/home` route + `_populate_contact_labels`, payment handler, deposit handler (local-routing rejection), signup/logout, and the currency filter.
- The strongest cross-check: make a transaction in one UI, then reload the other UI and confirm the same balance and history row. Backend state is shared, so both must agree.
- Amounts are stored in cents; both UIs must render dollars. Watch for a row whose account has no contact — Flask prints `None` in the Label column while a port may print the raw account number (cosmetic difference, worth noting).
- **Known failure mode to check for in any non-Flask client:** `ledgerwriter POST /transactions` returns HTTP 201 with the plain-text body `ok`, and `userservice POST /users` similarly returns non-JSON. Angular's `HttpClient` defaults to `responseType: 'json'`, so a *successful* call is delivered to the error callback (parse error) and the UI shows a false "failed" banner while the transaction actually commits. Always verify a "failed" transaction by reloading the page / checking the balance before believing the banner. Fix is `this.http.post(url, body, { responseType: 'text' })`.
- Validation edges worth exercising: amount `0`, negative, above balance, non-numeric and over-long account numbers, and submitting the "New external account" deposit with empty account/routing. Verify a user-visible message or field-level invalid styling appears and that no transaction is created (reload to confirm).
- Signup: the `birthday` field is `<input type="date">`; type the digits `01011990` (no slashes) after clicking it, otherwise the value stays empty and the form silently stays invalid.

## Forcing a genuine transaction failure through the UI
Most invalid inputs are blocked client-side (native `min`/`max`/`pattern`), so they never reach the backend. Two reliable ways to get a real server error banner:
- **Send a payment to your own account number** (choose "New recipient" and enter the logged-in account, e.g. `1011226111`). The contacts service answers HTTP 400 with `may not add yourself to contacts`; ledgerwriter has its own `can't send to self` check (`ExceptionMessages.java`) if a client skips contact creation. Good for verifying error text is human-readable and not `[object Object]`.
- **Scale a backend down**: `kubectl scale deployment/ledgerwriter --replicas=0`, submit a valid payment, then scale back to 1 (the Java pod needs ~90s to become Ready again). Caveats seen in practice: the request hangs for ~45s until nginx returns **504**, the SPA shows *no* pending/loading indicator while it hangs, and an nginx error page arrives as an HTML body — a client that renders `response.error` verbatim will dump raw HTML into the alert. Prefer mapping non-JSON/HTML error bodies to `HTTP <status>`.

## Verifying "updates in place" (no reload)
When checking that a SPA refreshes balance/history/contacts after a transaction, **never press F5** during the assertion — the backend commits either way, so only an in-place update distinguishes a working success path from a broken one. Note balancereader is eventually consistent (a client needs a short delay, ~250ms, before re-fetching), and after each success confirm three things: the balance delta, the new top history row, and (for new recipients/external accounts) the new entry in the corresponding dropdown, which proves contacts were re-fetched too.

## Coordinate drift when driving the UI
The alert banner sits above the cards, so a tall error message pushes the forms down and stale click coordinates land on the wrong field. Re-screenshot after any banner appears/disappears or after switching a dropdown to "New recipient"/"New external account" (which adds fields), and clear amount inputs with triple-click before typing — values persist across form-mode switches and typing appends.

## Verifying an in-flight / "submitting" state
Scaling `ledgerwriter` to 0 is the easiest way to get a long-running request (the proxied POST hangs ~45-90s before nginx returns 504), which gives a wide window to screenshot the pending UI. Assert three things in one in-flight screenshot: the progress alert text, the submit button's label change, and that the button is actually disabled. Note the app's CSS may not grey out a disabled button, so "disabled" looks identical to enabled — prove it functionally by clicking again during the flight and confirming no second alert appears and (after the request settles) no duplicate history row. Also check the *other* form's button, since a single shared `submitting` flag disables both. On the error path, confirm the progress alert disappears and the label reverts, otherwise the form stays permanently locked.

## Error bodies from the proxy
An unavailable backend produces an nginx HTML error page as a plain-text body; a hardened client should render only `HTTP <status>` (e.g. `Payment failed: HTTP 504`). When checking, look for `<html`, `504 Gateway Time-out</title>`, `nginx/`, or `a padding to disable MSIE` in the banner — their absence plus a single short line is the pass condition. Always also confirm the balance and top history row are unchanged, since the transaction must not have committed.

## Low-CPU hosts
`minikube start --cpus=4 --memory=8192` fails with `RSRC_INSUFFICIENT_CORES` on a 2-CPU box. Use `--cpus=$(nproc) --memory=5500` and delete non-essential deployments (`kubectl delete deployment loadgenerator`) to free CPU. Pods that look CrashLoopBackOff on first boot are often just resource churn — re-check before debugging.

## Rebuilding the Python service images from the working tree
A plain `docker build` in `src/frontend` (or `src/accounts/*`) copies a host `.venv` into the image, producing a `gunicorn` shebang that points at a host path and a container that will not start. Export a clean tree first:
`git archive HEAD:src/accounts/userservice | tar -x -C /tmp/us && cd /tmp/us && eval "$(minikube docker-env)" && docker build -t userservice:slack .`

## Which services the Angular SPA actually calls
`src/ui-angular/nginx/default.conf.template` proxies `/api/{userservice,balancereader,transactionhistory,contacts,ledgerwriter}/` **straight to the backends** — the Flask `frontend` is NOT on the Angular request path. Anything instrumented only in `frontend.py` cannot be exercised through the SPA; drive the Flask UI on :8080 for that. Reliable Angular-reachable backend error paths: bad password (`userservice /login`), duplicate username (`userservice /users`), payment to your own account (`contacts POST /contacts`).

## Testing outbound webhook / notification features
- Pods reach a host-side listener at the minikube bridge address **`192.168.49.1`** (e.g. `http://192.168.49.1:9000/hook`), so a tiny `http.server` on the host is enough to capture request bodies. Confirm the bridge IP with `minikube ip` / `ip route`.
- Keep two collector modes: one that replies `200` and one that accepts and **never replies**, to test outage safety. Verify the error path still returns, delayed at most by the configured timeout (`curl -w '%{time_total}'` is the cleanest evidence).
- To prove an opt-in feature makes **zero** calls, delete the secret, `kubectl rollout restart` the deployments, confirm the env var is absent in the *new* pod, clear the collector log, and assert it stays empty — an empty log distinguishes a real no-op from a silently failing POST.
- **Against a real third-party webhook (e.g. Slack) whose URL is a secret:** do not put the URL in the cluster secret if you also need to see the provider's reply. Instead run a small host-side *relay* that reads the URL from its own environment (bind it via the exec tool's `env` parameter, never echo it), forwards the request body verbatim, and logs the provider's status + response body. Point the cluster secret at the relay. This yields real delivery proof (`HTTP 200 "ok"` from Slack) without the URL ever appearing on screen, in a file, or in a recording. Follow up with one run where the secret holds the real URL directly to prove the pod itself can reach the provider — success there is evidenced by the *absence* of the service's send-failure warning in `kubectl logs`.
- Validate a webhook URL is live without posting a real message by POSTing a deliberately malformed body: Slack answers `400 invalid_payload` for a live URL and `404 invalid_token` for a rotated one.
- If the notification payload only sets a channel when a `SLACK_CHANNEL`-style var is non-empty, check the running pod (`kubectl exec ... printenv`) — when unset, messages route to the channel configured on the incoming webhook itself.

## Which UI to test
The Angular SPA (`src/ui-angular`, port-forward `svc/ui-angular 8081:80`) is the UI to demo/record for feature and bug-fix verification. Treat the Flask UI as a reference implementation only — do not record it. `ui-angular` is not in `kubernetes-manifests/`; build and deploy it explicitly:
`cd src/ui-angular && eval "$(minikube docker-env)" && docker build -t ui-angular:latest . && kubectl apply -k k8s/base` (the multi-stage npm build takes ~1 min even on 2 CPUs). It needs the `environment-config`, `service-api-config`, `demo-data-config` ConfigMaps from `kubernetes-manifests/config.yaml`.

## Java service caveat
The deployed `ledgerwriter` is usually the upstream released image (e.g. `v0.6.10`), so Java-side changes in the working tree are **not** running. Verify with `kubectl get deployment ledgerwriter -o jsonpath='{..image}'` before claiming any Java behavior was tested. Anything the upstream release predates (e.g. `TransactionValidator`'s recipient screening / SCREEN-403) simply cannot fire on that image, so even a config-only test needs a source build.

Building it locally is much cheaper than expected via jib (~1-2 min, no Dockerfile exists for this service):
`eval "$(minikube docker-env)" && ./mvnw -q -pl src/ledger/ledgerwriter -am -DskipTests -Dcheckstyle.skip=true compile jib:dockerBuild -Dimage=ledgerwriter:local`
Then test with a temp copy of the manifest whose `image:` is `ledgerwriter:local` plus `imagePullPolicy: Never`.

## Testing an env-var/config change in a manifest
Keep two temp copies of the manifest (e.g. `/tmp/lw/repro.yaml` with the old value, `/tmp/lw/fixed.yaml` with the new one) and flip between them with `kubectl apply` — this proves the old value reproduces the bug and the new one fixes it in the same cluster. Two gotchas:
- `kubectl apply -f <manifest>` **overwrites** any earlier `kubectl set env deployment --all ENABLE_TRACING=false ENABLE_METRICS=false`, so the new Java pod crashloops on `Your default credentials were not found` (Stackdriver). Bake `ENABLE_TRACING/ENABLE_METRICS: "false"` into the temp manifests.
- Confirm the value actually reached the running pod with `kubectl exec deploy/ledgerwriter -- printenv | grep SCREENED_ACCOUNTS` before trusting a UI result, and count log hits per pod (`kubectl logs deploy/ledgerwriter | grep -c 'SCREEN-403'`) to distinguish pre/post-fix pods.

### Flipping the value without a rollout
Every `kubectl apply` above costs a full ledgerwriter rollout (Spring Boot's graceful shutdown plus a JVM/context start), which dominates the run when the same value is flipped repeatedly. Instead, keep both variants warm and switch the `ledgerwriter` Service between them — no pod restart, and the change applies to the very next request:
- Generate two Deployments from the live one (`kubectl get deployment ledgerwriter -o json`), renaming them `ledgerwriter-screened` / `ledgerwriter-clean`, overriding `SCREENED_ACCOUNTS`, and adding a `variant: screened|clean` label to both `spec.selector.matchLabels` and the pod template.
- Scale the original `ledgerwriter` Deployment to 0 so only the labelled variants back the Service, then switch with `kubectl patch service ledgerwriter --type merge -p '{"spec":{"selector":{"variant":"clean"}}}'`.
- Verify the switch server-side rather than trusting the selector alone: the declining pod logs `Invalid transaction: Recipient screening declined` and the other logs `Submitted transaction successfully`.
- Restore by deleting the variants, removing `variant` from the Service selector, and scaling the original Deployment back to 1.

## Resetting polluted ledger data
`transactions` carries `prevent_delete`/`prevent_update` rules (append-only ledger), so scripted probes leave permanent rows that show up in balances and history. To clean up: `DROP RULE prevent_delete ON transactions;`, delete the rows, recreate the rule, then `kubectl rollout restart deploy/balancereader deploy/transactionhistory` — both cache aggressively and keep serving the old balance/history otherwise. Note `from_acct`/`to_acct` are `character(10)`, so match with `like '1055757655%'` rather than `=`.

## Devin Secrets Needed
- None for the standard flows. All app credentials are demo values baked into the manifests.
- `SLACK_WEBHOOK_URL` (session- or repo-scoped) only when testing the Slack error-notification feature against a real workspace. Note the scope actually granted may differ from what was requested — check `list_secrets` for the qualified reference before using it.
