using Ecom.Application.Services;
using Microsoft.AspNetCore.Mvc;

namespace Ecom.Api.Controllers;

[ApiController]
[Route("api/products")]
public class ProductsController(CatalogService catalogService) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> List()
    {
        var products = await catalogService.ListProductsAsync();
        return Ok(products);
    }
}
