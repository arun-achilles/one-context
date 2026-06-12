namespace Ecom.Application.DTOs;

public record AddToCartRequest(int UserId, int ProductId, int Quantity);
public record RemoveFromCartRequest(int UserId, int ProductId);
public record CheckoutRequest(int UserId);

public record CartItemDto(
    int ProductId,
    string Name,
    decimal Price,
    int Quantity,
    decimal LineTotal
);

public record CartDto(List<CartItemDto> Items, decimal Total);
public record CheckoutResponse(int OrderId, string Status, decimal Total);
