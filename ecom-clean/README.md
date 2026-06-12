# Ecom Clean Demo (.NET + React)

This ecommerce demo uses:

- Backend: .NET 8 Web API with clean architecture
- Frontend: React (Vite)
- DB: SQLite via EF Core

## Features

- Browse products
- Add/remove cart items
- Checkout (mock payment)
- Order history

## Backend structure

- `backend-dotnet/src/Ecom.Domain`: entities, repository contracts
- `backend-dotnet/src/Ecom.Application`: use-cases/services and DTOs
- `backend-dotnet/src/Ecom.Infrastructure`: EF Core DbContext, repositories, seed data
- `backend-dotnet/src/Ecom.Api`: controllers and app startup

## Run backend

```bash
cd ecom-clean/backend-dotnet/src/Ecom.Api
dotnet run
```

API runs at `http://localhost:8081`.

Useful endpoints:

- `GET /api/products`
- `POST /api/cart/items`
- `DELETE /api/cart/items`
- `GET /api/cart/{userId}`
- `POST /api/checkout`
- `GET /api/orders/{userId}`

## Run frontend

```bash
cd ecom-clean/frontend-react
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and calls the backend at `http://localhost:8081/api`.

## Demo user

- `userId = 1` (seeded automatically)

## One Context ingestion setup

Use `ecom-clean/onecontext.ecom.yaml` and point your code source to `ecom-clean`.
