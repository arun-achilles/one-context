using Ecom.Application.DTOs;
using Ecom.Domain.Entities;
using Ecom.Domain.Repositories;

namespace Ecom.Application.Services;

public class CartService(
    ICartRepository cartRepository,
    IProductRepository productRepository,
    IOrderRepository orderRepository)
{
    public async Task AddToCartAsync(AddToCartRequest request)
    {
        if (request.Quantity <= 0)
        {
            throw new ArgumentException("quantity must be positive");
        }

        var product = await productRepository.GetByIdAsync(request.ProductId);
        if (product is null)
        {
            throw new InvalidOperationException("product not found");
        }

        if (product.Stock < request.Quantity)
        {
            throw new InvalidOperationException("insufficient stock");
        }

        var existing = await cartRepository.GetItemAsync(request.UserId, request.ProductId);
        if (existing is null)
        {
            await cartRepository.AddAsync(new CartItem
            {
                UserId = request.UserId,
                ProductId = request.ProductId,
                Quantity = request.Quantity
            });
            return;
        }

        existing.Quantity += request.Quantity;
        await cartRepository.UpdateAsync(existing);
    }

    public async Task RemoveFromCartAsync(RemoveFromCartRequest request)
    {
        var existing = await cartRepository.GetItemAsync(request.UserId, request.ProductId);
        if (existing is null)
        {
            return;
        }

        await cartRepository.RemoveAsync(existing);
    }

    public async Task<CartDto> GetCartAsync(int userId)
    {
        var items = await cartRepository.ListByUserAsync(userId);
        var result = new List<CartItemDto>();
        decimal total = 0;

        foreach (var item in items)
        {
            var product = item.Product;
            if (product is null)
            {
                continue;
            }

            var lineTotal = product.Price * item.Quantity;
            total += lineTotal;
            result.Add(new CartItemDto(
                product.Id,
                product.Name,
                product.Price,
                item.Quantity,
                lineTotal
            ));
        }

        return new CartDto(result, total);
    }

    public async Task<CheckoutResponse> CheckoutAsync(CheckoutRequest request)
    {
        var cart = await GetCartAsync(request.UserId);
        if (!cart.Items.Any())
        {
            throw new InvalidOperationException("cart is empty");
        }

        var order = new Order
        {
            UserId = request.UserId,
            TotalAmount = cart.Total,
            Status = "PLACED",
            CreatedAt = DateTime.UtcNow,
            Items = cart.Items.Select(item => new OrderItem
            {
                ProductId = item.ProductId,
                Quantity = item.Quantity,
                UnitPrice = item.Price
            }).ToList()
        };

        foreach (var item in cart.Items)
        {
            var product = await productRepository.GetByIdAsync(item.ProductId)
                          ?? throw new InvalidOperationException("product not found during checkout");

            if (product.Stock < item.Quantity)
            {
                throw new InvalidOperationException($"insufficient stock for {product.Name}");
            }

            product.Stock -= item.Quantity;
            await productRepository.UpdateAsync(product);
        }

        await orderRepository.AddAsync(order);
        await cartRepository.ClearByUserAsync(request.UserId);

        return new CheckoutResponse(order.Id, order.Status, order.TotalAmount);
    }
}
