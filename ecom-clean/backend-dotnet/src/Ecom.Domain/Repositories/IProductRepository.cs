using Ecom.Domain.Entities;

namespace Ecom.Domain.Repositories;

public interface IProductRepository
{
    Task<List<Product>> ListAsync();
    Task<Product?> GetByIdAsync(int productId);
    Task UpdateAsync(Product product);
}
