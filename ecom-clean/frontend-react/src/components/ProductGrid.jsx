export default function ProductGrid({ products, onAdd }) {
  return (
    <section className="panel">
      <h2>Products</h2>
      <div className="grid">
        {products.map((product) => (
          <article key={product.id} className="card">
            <h3>{product.name}</h3>
            <p>{product.description}</p>
            <div className="meta">
              <span>${Number(product.price).toFixed(2)}</span>
              <small>Stock: {product.stock}</small>
            </div>
            <button onClick={() => onAdd(product.id)}>Add to cart</button>
          </article>
        ))}
      </div>
    </section>
  );
}
