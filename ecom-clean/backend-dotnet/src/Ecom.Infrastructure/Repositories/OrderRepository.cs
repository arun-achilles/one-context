using Ecom.Domain.Entities;
using Ecom.Domain.Repositories;
using Ecom.Infrastructure.Data;
using Microsoft.EntityFrameworkCore;

namespace Ecom.Infrastructure.Repositories;

public class OrderRepository(EcomDbContext dbContext) : IOrderRepository
{
    public async Task AddAsync(Order order)
    {
        dbContext.Orders.Add(order);
        await dbContext.SaveChangesAsync();
    }

    public Task<List<Order>> ListByUserAsync(int userId)
    {
        return dbContext.Orders
            .Include(order => order.Items)
            .Where(order => order.UserId == userId)
            .OrderByDescending(order => order.CreatedAt)
            .ToListAsync();
    }
}
