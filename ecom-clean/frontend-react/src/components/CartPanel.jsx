export default function CartPanel({ cart, onRemove, onCheckout }) {
  return (
    <section className="panel">
      <h2>Cart</h2>
      {!cart.items.length ? (
        <p className="empty">Cart is empty.</p>
      ) : (
        <>
          {cart.items.map((item) => (
            <div key={item.productId} className="row">
              <div>
                <strong>{item.name}</strong>
                <small> x{item.quantity}</small>
              </div>
              <div className="row-actions">
                <span>${Number(item.lineTotal).toFixed(2)}</span>
                <button className="danger" onClick={() => onRemove(item.productId)}>Remove</button>
              </div>
            </div>
          ))}
          <p className="total">Total: ${Number(cart.total).toFixed(2)}</p>
          <button onClick={onCheckout}>Checkout (mock payment)</button>
        </>
      )}
    </section>
  );
}
