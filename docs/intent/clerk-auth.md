# Intent — Access Gating for Public Deployment

Date: —  
Topic: originally "add Clerk authentication"

## The original ask vs. what was actually wanted

The request started as *"I'm planning on adding Clerk authentication to this app."*
Through interview it emerged that Clerk was a convention the user reached for ("it
would be cool") rather than a product need. No functional requirement pointed at
Clerk. The interview surfaced what the auth was actually for.

## Established facts

- **Single user**: this is a personal tool. Only the owner ever logs in. There is no
  multi-user, no per-user data, no orgs, no roles.
- **Private today, public tomorrow**: the backend (port 8001) is currently deployed
  with zero auth and CORS open. The plan is to host the app on Vercel so it can be
  showcased.
- **Showcase context**: the app is a portfolio piece shown to prospective employers.
  The owner demos it live *while logged in* — employers watch the screen and never
  touch the login flow.

## The core insight

In a live demo the login gate is **invisible** to the employer — they watch the owner
already signed in. So the "cool factor" of a full auth platform never actually
surfaces. Meanwhile Clerk's signup ceremony would have been dead weight: unnecessary
setup, a friction wall, and zero functional payoff for a single-user app.

The only *real* job of access control here is to **keep strangers from hitting the
publicly-hosted app and burning the owner's OpenRouter/API budget.**

## Confirmed intent

```
Outcome:      host on Vercel, gate it so strangers can't burn OpenRouter credits
User:         only the owner logs in; employers watch the owner's live screen
Why now:      deploying publicly — first time anyone outside could reach it
Success:      stranger hits it → blocked; owner opens it → clean in, zero signup dance
Constraint:   single user, no accounts / orgs / roles needed
Out of scope: Clerk, Google SSO, accounts, orgs, per-user data, employer accounts
```

## Decision

**Plain gate** — not Clerk.

Chosen over the "Clerk-lite" option (Clerk + Google SSO, single allowlisted account,
magic link). Plain gate delivers the entire payoff (keep the internet out, let the
owner in frictionlessly) at a fraction of the cost and complexity.

Concrete options for implementation (not yet selected — nothing is built yet):

- **Vercel Protected Routes / password**: simplest, zero new deps, handled at the
  platform layer.
- **Shared secret on the backend**: gate the API itself with a token/allowlist so
  forged requests can't reach stages 1–3 and burn credits even if the frontend is
  public.
- **Deployed security**: in all cases, remove/replace the open CORS + unauthenticated
  port 8001 exposure once Vercel handles distribution.

## Current status

Intent recorded only. **No implementation.** Next step when ready: pick a gate
mechanism and write a spec.

## Why this matters (the lesson)

"Add Clerk" was a should-want. The underlying want was *deploy publicly without
letting strangers drain API credits*. The cheapest correct tool for that want is not
a full auth platform. Confirming intent before building avoided days of needless
wiring.
