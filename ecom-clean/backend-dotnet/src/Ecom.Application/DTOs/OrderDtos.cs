namespace Ecom.Application.DTOs;

public record OrderDto(int Id, decimal TotalAmount, string Status, DateTime CreatedAt);
