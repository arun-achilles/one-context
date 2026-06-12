using Ecom.Domain.Entities;

namespace Ecom.Domain.Repositories;

public interface IOrderRepository
{
    Task AddAsync(Order order);
    Task<List<Order>> ListByUserAsync(int userId);
}
