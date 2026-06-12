using Ecom.Application.DTOs;
using Ecom.Domain.Repositories;

namespace Ecom.Application.Services;

public class OrderService(IOrderRepository orderRepository)
{
    public async Task<List<OrderDto>> ListOrdersAsync(int userId)
    {
        var orders = await orderRepository.ListByUserAsync(userId);
        return orders
            .OrderByDescending(order => order.CreatedAt)
            .Select(order => new OrderDto(order.Id, order.TotalAmount, order.Status, order.CreatedAt))
            .ToList();
    }
}
