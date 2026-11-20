# Simplified Price Checker Backend Service API

A versioned FastAPI backend for store price submissions and shopper price comparisons. It uses Clean Architecture, SQLAlchemy repositories, SQLite by default, role-based JWT authentication, and a replaceable price-label strategy.

> **Development/demo notice:** Local HTTP is not encrypted. Store prices are only data entered by store accounts; this project does not connect to real retailer systems. Before deployment, configure HTTPS at a trusted reverse proxy, set a private `JWT_SECRET`, and use an appropriate production database.

## Requirements

- Python 3.10+
- PowerShell on Windows (or a terminal on Linux/macOS)

## Run locally on Windows

Open a terminal in the project root (the folder containing `requirements.txt`), then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

By default, local development automatically approves store registrations so you can test the frontend without first creating an admin. To test the admin approval workflow instead, disable this demo behavior and create the first admin account. The command creates the SQLite database if needed and asks for a password without displaying it:

```powershell
$env:AUTO_APPROVE_STORES = "false"
python -m app.infrastructure.bootstrap_admin
```

Start the API:

```powershell
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/** for the browser application or **http://127.0.0.1:8000/docs** for interactive Swagger/OpenAPI. Keep the terminal open while using the application; press **Ctrl+C** to stop the server. The database is `price_checker.db` in the current working directory by default.

The browser application provides shopper and store registration, sign-in, shopper price comparison, store price and discount submission, and admin store approvals and management. In development, store accounts are automatically approved by default, so the first admin is optional when trying shopper and store features. Set `AUTO_APPROVE_STORES=false` and bootstrap an admin to test manual store approval. Auto-approval is rejected outside `APP_ENV=development`; never enable it for production. An admin is still needed to use the administration workspace.

For PowerShell environments where activating a virtual environment is blocked, run the commands using `.\.venv\Scripts\python.exe -m ...`.

## Authentication and account approval

All API paths are under `/api/v1`.

1. A shopper registers at `POST /api/v1/auth/register/shopper` and can log in immediately.
2. A store registers at `POST /api/v1/auth/register/store` with its store name and latitude/longitude. The account remains pending until approved.
3. The first admin is created locally with the bootstrap command above. Admins can view and approve store requests, lock/unlock or remove store accounts, create other admins, and inspect audit logs.
4. Use `POST /api/v1/auth/login` with the account username and password. In Swagger, click **Authorize** and paste the returned access token. Tokens expire after 60 minutes.

Passwords are stored as PBKDF2-SHA256 hashes, never as plain text. The development JWT secret is intentionally unsuitable for deployment. Set `APP_ENV=production` and a private `JWT_SECRET` of at least 32 characters in the server environment. Serve production traffic over HTTPS; TLS is expected to be configured by the deployment/proxy.

## Main endpoints

| Endpoint | Required role | Description |
|---|---|---|
| `POST /api/v1/auth/register/shopper` | Public | Create an active shopper account |
| `POST /api/v1/auth/register/store` | Public | Create a pending store account |
| `POST /api/v1/auth/login` | Public | Log in and get a JWT |
| `GET /api/v1/admin/stores/pending` | Admin | List stores awaiting approval |
| `POST /api/v1/admin/stores/{id}/approve` | Admin | Approve a store |
| `POST /api/v1/admin/stores/{id}/lock` | Admin | Lock a store account |
| `POST /api/v1/admin/stores/{id}/unlock` | Admin | Unlock a store account |
| `DELETE /api/v1/admin/stores/{id}` | Admin | Remove a store account and its prices/discounts |
| `POST /api/v1/admin/admins` | Admin | Create another administrator |
| `GET /api/v1/admin/audit-logs` | Admin | Read timestamped admin audit entries |
| `POST /api/v1/stores/prices` | Approved store | Submit one price |
| `POST /api/v1/stores/prices/batch` | Approved store | Submit 1–1,000 prices in one request |
| `POST /api/v1/stores/discounts` | Approved store | Create an app-user discount |
| `POST /api/v1/prices/compare` | Shopper | Save a shopper search and find nearby current prices |

Store price and shopper comparison requests contain `barcode_type`, digit-string `gtin`, a positive price, and a timezone-aware timestamp. Supported barcode types are `GTIN`, `EAN`, and `UPC`. Store coordinates are supplied at registration; shopper comparison requests include latitude, longitude, and optional `nearby_km` (default 10 km). Coordinates outside valid latitude/longitude ranges are rejected.

Example shopper comparison request:

```json
{
  "barcode_type": "EAN",
  "gtin": "0123456789012",
  "price": "12.50",
  "latitude": 60.4518,
  "longitude": 22.2666,
  "timestamp": "2026-11-16T08:30:00Z",
  "nearby_km": 10
}
```

The response contains the latest price from each approved, unlocked store within the radius, sorted by current price. Active store discounts are applied only in the authenticated shopper comparison response. Labels are calculated relative to the shopper's submitted price: **Very inexpensive**, **Inexpensive**, **Similar price**, **Expensive**, or **Very expensive**.

## Browser application

The same FastAPI server serves a single-page browser client from `app/frontend/index.html`. It keeps the login token in the current browser tab's session storage and sends it as a Bearer token to protected API endpoints. Shopper/store/admin workspaces are shown based on the role returned by the API login response.

## Architecture

```text
app/
  api/              FastAPI routers, request/response schemas, auth dependencies
  application/      Use cases/services and repository/token/password ports
  domain/           Entities, errors, and price-label Strategy
  infrastructure/   SQLAlchemy models, SQLite/MySQL-compatible repositories,
                    JWT/password implementations, database setup
```

Dependencies point inward: the Domain has no imports from the other application layers; Application depends on Domain and ports; Infrastructure implements the ports; API and dependency wiring connect the application to infrastructure.

The `PriceLabelStrategy` allows price-label rules to be replaced without editing the comparison service. `RelativePriceLabelStrategy` is the current implementation. Repository interfaces keep application services independent of the ORM and database.

## Database configuration and portability

SQLite is the default. Set `DATABASE_URL` before starting the API to select another SQLAlchemy database URL. PyMySQL is included for a MySQL-compatible URL, for example:

```powershell
$env:DATABASE_URL = "mysql+pymysql://user:password@host/database"
```

Do not put real passwords in source control or shared terminal history. SQLite and MySQL/MariaDB require integration testing and deployment-specific schema migration before production. Tables are currently initialized with SQLAlchemy `create_all`; a migration framework is not included.

## Validation and tests

Run all tests:

```powershell
python -m pytest
```

The suite covers role authorization, store approval, price/discount workflows, invalid input, audit entries, hashed passwords, and AST-based import fitness checks that prevent Domain and Application from depending on outer layers. Isolated Application tests use in-memory fakes (no database) for authentication and administration, and verify a new price-label strategy can be substituted without changing the comparison service. It also generates 10,000 price records and checks that the p95 comparison response time is below one second across 100 in-process test requests. This is a local regression/load check, not a substitute for a production network load test.
