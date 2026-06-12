using Ecom.Domain.Entities;
using Ecom.Domain.Repositories;
using Ecom.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;

namespace Ecom.Infrastructure.Repositories;

public class ProductRepository(EcomDbContext dbContext) : IProductRepository
{
    public Task<List<Product>> ListAsync() => dbContext.Products.OrderBy(product => product.Id).ToListAsync();

    public Task<Product?> GetByIdAsync(int productId) => dbContext.Products.FirstOrDefaultAsync(product => product.Id == productId);

    public async Task UpdateAsync(Product product)
    {
        dbContext.Products.Update(product);
        await dbContext.SaveChangesAsync();
    }
}
