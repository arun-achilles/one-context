using Ecom.Domain.Entities;

namespace Ecom.Infrastructure.Data;

public static class DbSeeder
{
    public static async Task SeedAsync(EcomDbContext dbContext)
    {
        if (dbContext.Users.Any() || dbContext.Products.Any())
        {
            return;
        }

        dbContext.Users.Add(new User
        {
            Id = 1,
            Email = "demo@northstar.local",
            FullName = "Demo Shopper"
        });

        dbContext.Products.AddRange(
            new Product { Sku = "SKU-BAG-001", Name = "Everyday Backpack", Description = "Water-resistant commuter backpack", Price = 59.99m, Stock = 40 },
            new Product { Sku = "SKU-WAT-001", Name = "Insulated Bottle", Description = "750ml stainless steel bottle", Price = 24.50m, Stock = 120 },
            new Product { Sku = "SKU-HDP-001", Name = "Wireless Headphones", Description = "Noise-cancelling over-ear headphones", Price = 149.00m, Stock = 25 },
            new Product { Sku = "SKU-TEE-001", Name = "Organic Cotton Tee", Description = "Soft unisex crew neck tee", Price = 19.90m, Stock = 200 },
            new Product { Sku = "SKU-MSE-001", Name = "Ergo Mouse", Description = "Vertical ergonomic mouse", Price = 39.00m, Stock = 70 },
            new Product { Sku = "SKU-KEY-001", Name = "Mechanical Keyboard", Description = "Compact tactile mechanical keyboard", Price = 89.00m, Stock = 32 }
        );

        await dbContext.SaveChangesAsync();
    }
}
