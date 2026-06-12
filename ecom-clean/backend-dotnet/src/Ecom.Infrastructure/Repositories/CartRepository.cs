using Ecom.Domain.Entities;
using Ecom.Domain.Repositories;
using Ecom.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;

namespace Ecom.Infrastructure.Repositories;

public class CartRepository(EcomDbContext dbContext) : ICartRepository
{
    public Task<List<CartItem>> ListByUserAsync(int userId)
    {
        return dbContext.CartItems
            .Include(cartItem => cartItem.Product)
            .Where(cartItem => cartItem.UserId == userId)
            .OrderBy(cartItem => cartItem.Id)
            .ToListAsync();
    }

    public Task<CartItem?> GetItemAsync(int userId, int productId)
    {
        return dbContext.CartItems
            .FirstOrDefaultAsync(cartItem => cartItem.UserId == userId && cartItem.ProductId == productId);
    }

    public async Task AddAsync(CartItem item)
    {
        dbContext.CartItems.Add(item);
        await dbContext.SaveChangesAsync();
    }

    public async Task UpdateAsync(CartItem item)
    {
        dbContext.CartItems.Update(item);
        await dbContext.SaveChangesAsync();
    }

    public async Task RemoveAsync(CartItem item)
    {
        dbContext.CartItems.Remove(item);
        await dbContext.SaveChangesAsync();
    }

    public async Task ClearByUserAsync(int userId)
    {
        var items = await dbContext.CartItems.Where(cartItem => cartItem.UserId == userId).ToListAsync();
        dbContext.CartItems.RemoveRange(items);
        await dbContext.SaveChangesAsync();
    }
}
