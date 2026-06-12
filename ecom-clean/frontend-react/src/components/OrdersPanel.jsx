export default function OrdersPanel({ orders }) {
  return (
    <section className="panel full-width">
      <h2>Order History</h2>
      {!orders.length ? (
        <p className="empty">No orders yet.</p>
      ) : (
        orders.map((order) => (
          <div key={order.id} className="row">
            <div>
              <strong>Order #{order.id}</strong>
              <small> {new Date(order.createdAt).toLocaleString()}</small>
            </div>
            <div>
              <span>{order.status}</span>
              <strong className="order-amount"> ${Number(order.totalAmount).toFixed(2)}</strong>
            </div>
          </div>
        ))
      )}
    </section>
  );
}
