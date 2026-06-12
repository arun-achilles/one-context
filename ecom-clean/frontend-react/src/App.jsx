import { useEffect, useState } from "react";
import { api } from "./api/client";
import ProductGrid from "./components/ProductGrid";
import CartPanel from "./components/CartPanel";
import OrdersPanel from "./components/OrdersPanel";

const USER_ID = 1;

export default function App() {
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState({ items: [], total: 0 });
  const [orders, setOrders] = useState([]);
  const [error, setError] = useState("");

  async function refreshAll() {
    const [productData, cartData, orderData] = await Promise.all([
      api.listProducts(),
      api.getCart(USER_ID),
      api.getOrders(USER_ID)
    ]);
    setProducts(productData);
    setCart(cartData);
    setOrders(orderData);
  }

  useEffect(() => {
    refreshAll().catch((err) => setError(err.message));
  }, []);

  async function handleAddToCart(productId) {
    setError("");
    try {
      await api.addToCart({ userId: USER_ID, productId, quantity: 1 });
      await refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRemoveFromCart(productId) {
    setError("");
    try {
      await api.removeFromCart({ userId: USER_ID, productId });
      await refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCheckout() {
    setError("");
    try {
      await api.checkout({ userId: USER_ID });
      await refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>Northstar Commerce</h1>
        <p>React + .NET clean architecture demo</p>
      </header>

      {error && <div className="error">{error}</div>}

      <main className="layout">
        <ProductGrid products={products} onAdd={handleAddToCart} />
        <CartPanel cart={cart} onRemove={handleRemoveFromCart} onCheckout={handleCheckout} />
        <OrdersPanel orders={orders} />
      </main>
    </div>
  );
}
