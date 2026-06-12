using Ecom.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace Ecom.Infrastructure.Data;

public class EcomDbContext(DbContextOptions<EcomDbContext> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();
    public DbSet<Product> Products => Set<Product>();
    public DbSet<CartItem> CartItems => Set<CartItem>();
    public DbSet<Order> Orders => Set<Order>();
    public DbSet<OrderItem> OrderItems => Set<OrderItem>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<CartItem>()
            .HasIndex(cartItem => new { cartItem.UserId, cartItem.ProductId })
            .IsUnique();

        modelBuilder.Entity<CartItem>()
            .HasOne(cartItem => cartItem.Product)
            .WithMany()
            .HasForeignKey(cartItem => cartItem.ProductId);

        modelBuilder.Entity<Order>()
            .HasMany(order => order.Items)
            .WithOne()
            .HasForeignKey(orderItem => orderItem.OrderId);

        modelBuilder.Entity<OrderItem>()
            .HasOne(orderItem => orderItem.Product)
            .WithMany()
            .HasForeignKey(orderItem => orderItem.ProductId);
    }
}
