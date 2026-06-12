using Ecom.Application.Services;
using Microsoft.AspNetCore.Mvc;

namespace Ecom.Api.Controllers;

[ApiController]
[Route("api/orders")]
public class OrdersController(OrderService orderService) : ControllerBase
{
    [HttpGet("{userId:int}")]
    public async Task<IActionResult> List([FromRoute] int userId)
    {
        var orders = await orderService.ListOrdersAsync(userId);
        return Ok(orders);
    }
}
