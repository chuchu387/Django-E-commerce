from django.db import models
from django.contrib.auth.models import User


# Create your models here.

class Admin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=50)
    image = models.ImageField(upload_to="admins")
    mobile = models.CharField(max_length=20)

    def __str__(self):
        return self.user.username

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=200)
    address = models.CharField(max_length=200, null=True, blank=True)

    #whenever customer register it will provide the joined date
    joined_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name


class Category(models.Model): #this Model calss is inheriated in this category class.
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)

    #whenever we call the object of category so it can return its title so we can recognize it
    def __str__(self):
        return self.title


class Product(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)

    #while uploading products we need category so i create category as a field
    #foreignkey means that category object means that
    #1. a category have many products but
    #2. a product have only one category
    #cascade means whenever i delete category mean all the products related to that category is deleted(set_null)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    image = models.ImageField(upload_to='products')
    marked_price = models.PositiveIntegerField()
    selling_price = models.PositiveIntegerField()
    description = models.TextField()
    return_policy = models.CharField(max_length=300, null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title


#this means a customer may have many carts but a cart is of for only on customer
#1. so i use null=True because i want unauthenticated user also can create cart or add product to the cart
#2. it means no login is required while creating the cart or adding products to the cart
class Cart(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.PositiveIntegerField(default=0)

    #auto_now_add = true because cart created date is automatically save
    created_at = models.DateTimeField(auto_now_add=True)

    #it return cart and cartID
    def __str__(self):
        return "Cart: " + str(self.id)

#CartProduct is different form product
#1. if user put product in cart that is actually cart product
class CartProduct(models.Model):

    #this Foreignkey implies that a Cart may have many cart product
    #1. if user delete the cart all the cartproduct related to that cart is deleted
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rate = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    subtotal = models.PositiveIntegerField()

    #it shows firstly
    #1. self means CartProduct object
    #2. cart means the cart object => cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    #3. id means the Cart ID
    def __str__(self):
        return "Product: " + str(self.cart.id) + "CartProduct: " + str(self.id)

ORDER_STATUS = (
    ("Order Recieved", "Order Recieved"),
    ("Order Processing", "Order Processing"),
    ("On the way", "On the way"),
    ("Order Completed", "Order Completed"),
    ("Order Cancelled", "Order Cancelled"),
)

METHOD = (
    ("Cash On Delivery", "Cash On Delivery"),
    ("Khalti", "Khalti"),
)

#is cart is cheackedout then order must be stored in order table
class Order(models.Model):
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE)
    ordered_by = models.CharField(max_length=200)
    shipping_address = models.CharField(max_length=200)
    mobile = models.CharField(max_length=10)
    email = models.EmailField(null=True, blank=True)
    subtotal = models.PositiveIntegerField()

    #discount means like a cupon code also
    discount = models.PositiveIntegerField()

    #subtotal - discount = Total amount
    total = models.PositiveIntegerField()
    order_status = models.CharField(max_length=200, choices=ORDER_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, choices=METHOD, default="Cash On Delivery")
    payment_completed = models.BooleanField(default=False, null=True, blank=True)

    def __str__(self):
        return "Order: " + str(self.id)
