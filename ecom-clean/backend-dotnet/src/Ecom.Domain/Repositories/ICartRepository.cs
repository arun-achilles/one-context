using Ecom.Domain.Entities;

namespace Ecom.Domain.Repositories;

public interface ICartRepository
{
    Task<List<CartItem>> ListByUserAsync(int userId);
    Task<CartItem?> GetItemAsync(int userId, int productId);
    Task AddAsync(CartItem item);
    Task UpdateAsync(CartItem item);
    Task RemoveAsync(CartItem item);
    Task ClearByUserAsync(int userId);
}
