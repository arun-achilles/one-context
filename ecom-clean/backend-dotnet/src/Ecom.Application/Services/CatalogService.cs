using Ecom.Domain.Entities;
using Ecom.Domain.Repositories;

namespace Ecom.Application.Services;

public class CatalogService(IProductRepository productRepository)
{
    public Task<List<Product>> ListProductsAsync() => productRepository.ListAsync();
}
