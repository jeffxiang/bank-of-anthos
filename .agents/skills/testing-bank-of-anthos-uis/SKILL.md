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

## Devin Secrets Needed
- None. All credentials are demo values baked into the manifests.
