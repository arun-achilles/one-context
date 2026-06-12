using Ecom.Application.DTOs;
using Ecom.Application.Services;
using Microsoft.AspNetCore.Mvc;

namespace Ecom.Api.Controllers;

[ApiController]
[Route("api")]
public class CartController(CartService cartService) : ControllerBase
{
    [HttpPost("cart/items")]
    public async Task<IActionResult> AddItem([FromBody] AddToCartRequest request)
    {
        try
        {
            await cartService.AddToCartAsync(request);
            return Ok(new { message = "added to cart" });
        }
        catch (Exception exception)
        {
            return BadRequest(new { detail = exception.Message });
        }
    }

    [HttpDelete("cart/items")]
    public async Task<IActionResult> RemoveItem([FromBody] RemoveFromCartRequest request)
    {
        await cartService.RemoveFromCartAsync(request);
        return Ok(new { message = "removed from cart" });
    }

    [HttpGet("cart/{userId:int}")]
    public async Task<IActionResult> GetCart([FromRoute] int userId)
    {
        var cart = await cartService.GetCartAsync(userId);
        return Ok(cart);
    }

    [HttpPost("checkout")]
    public async Task<IActionResult> Checkout([FromBody] CheckoutRequest request)
    {
        try
        {
            var result = await cartService.CheckoutAsync(request);
            return Ok(result);
        }
        catch (Exception exception)
        {
            return BadRequest(new { detail = exception.Message });
        }
    }
}
