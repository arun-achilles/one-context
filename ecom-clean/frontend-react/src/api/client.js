const API_BASE = "http://localhost:8081/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Request failed");
  }
  return response.json();
}

export const api = {
  listProducts: () => request("/products"),
  addToCart: (payload) => request("/cart/items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  removeFromCart: (payload) => request("/cart/items", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  getCart: (userId) => request(`/cart/${userId}`),
  checkout: (payload) => request("/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  getOrders: (userId) => request(`/orders/${userId}`)
};
