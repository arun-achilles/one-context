using Ecom.Application.Services;
using Ecom.Domain.Repositories;
using Ecom.Infrastructure.Data;
using Ecom.Infrastructure.Repositories;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddDbContext<EcomDbContext>(options =>
    options.UseSqlite("Data Source=ecom-clean.db"));

builder.Services.AddScoped<IProductRepository, ProductRepository>();
builder.Services.AddScoped<ICartRepository, CartRepository>();
builder.Services.AddScoped<IOrderRepository, OrderRepository>();

builder.Services.AddScoped<CatalogService>();
builder.Services.AddScoped<CartService>();
builder.Services.AddScoped<OrderService>();

builder.Services.AddCors(options =>
{
    options.AddPolicy("frontend", policy =>
        policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod());
});

var app = builder.Build();

using (var scope = app.Services.CreateScope())
{
    var dbContext = scope.ServiceProvider.GetRequiredService<EcomDbContext>();
    await dbContext.Database.EnsureCreatedAsync();
    await DbSeeder.SeedAsync(dbContext);
}

app.UseSwagger();
app.UseSwaggerUI();
app.UseCors("frontend");
app.MapControllers();

app.MapGet("/api/health", () => Results.Ok(new { status = "ok" }));

app.Run();
