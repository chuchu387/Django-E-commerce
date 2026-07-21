from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


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
    joined_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class DeliveryZone(models.Model):
    name = models.CharField(max_length=100)
    areas_description = models.TextField(help_text="Areas covered in this zone")
    fee = models.PositiveIntegerField(default=80, help_text="Delivery fee for this zone")
    min_order_for_free_delivery = models.PositiveIntegerField(default=999, help_text="Orders above this amount get free delivery")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Address(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=200)
    mobile = models.CharField(max_length=20)
    street_address = models.CharField(max_length=300, help_text="Street, area, landmark")
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    label = models.CharField(max_length=50, default="Home", help_text="e.g. Home, Work, Other")
    delivery_zone = models.ForeignKey(DeliveryZone, on_delete=models.SET_NULL, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.label}: {self.street_address}, {self.city}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(customer=self.customer, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name="vendor")
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    logo = models.ImageField(upload_to="vendors", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=300, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_on_vacation = models.BooleanField(default=False, help_text="When enabled, all products are temporarily unavailable")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def is_open_now(self):
        now = timezone.now()
        today_hours = self.business_hours.filter(day=now.weekday()).first()
        if not today_hours:
            return True
        if today_hours.is_closed:
            return False
        if today_hours.open_time and today_hours.close_time:
            current = now.time()
            return today_hours.open_time <= current <= today_hours.close_time
        return True


WEEKDAYS = (
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
)


class VendorBusinessHour(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="business_hours")
    day = models.IntegerField(choices=WEEKDAYS)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False, help_text="Tick if closed all day")

    class Meta:
        unique_together = ("vendor", "day")
        ordering = ["day"]

    def __str__(self):
        if self.is_closed:
            return f"{self.vendor.name} — {self.get_day_display()}: Closed"
        return f"{self.vendor.name} — {self.get_day_display()}: {self.open_time}–{self.close_time}"


class Category(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = "categories"


class Product(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)

    image = models.ImageField(upload_to='products')
    marked_price = models.PositiveIntegerField()
    selling_price = models.PositiveIntegerField()
    description = models.TextField()
    return_policy = models.CharField(max_length=300, null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)

    stock = models.PositiveIntegerField(default=0, help_text="Current inventory count (0 = out of stock)")
    low_stock_threshold = models.PositiveIntegerField(default=5, help_text="Alert when stock falls below this")
    is_available = models.BooleanField(default=True, help_text="Uncheck to mark as sold out")
    is_hidden = models.BooleanField(default=False, help_text="Hide from all customer listings")
    is_approved = models.BooleanField(default=False, help_text="Admin must approve before product goes live")
    available_from = models.DateTimeField(null=True, blank=True, help_text="Scheduled availability start")
    available_until = models.DateTimeField(null=True, blank=True, help_text="Scheduled availability end")
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.stock == 0:
            self.is_available = False
        super().save(*args, **kwargs)

    @property
    def is_sold_out(self):
        return not self.is_available or self.stock == 0

    @property
    def is_available_for_purchase(self):
        if self.is_hidden:
            return False
        if not self.is_approved:
            return False
        if not self.is_available:
            return False
        if self.stock == 0:
            return False
        if self.vendor and self.vendor.is_on_vacation:
            return False
        if self.vendor and not self.vendor.is_open_now():
            return False
        now = timezone.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True

    @property
    def average_rating(self):
        ratings = self.review_set.filter(is_approved=True).values_list("rating", flat=True)
        if ratings:
            return round(sum(ratings) / len(ratings), 1)
        return None

    @property
    def review_count(self):
        return self.review_set.filter(is_approved=True).count()


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/images/")

    def __str__(self):
        return self.product.title


class Review(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("customer", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} - {self.product} ({self.rating}*)" if self.is_approved else f"[Pending] {self.customer} - {self.product}"


class Referral(models.Model):
    referrer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="referrals_made")
    referred = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="referred_by")
    coupon = models.ForeignKey("Coupon", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reward_given = models.BooleanField(default=False)

    class Meta:
        unique_together = ("referrer", "referred")

    def __str__(self):
        return f"{self.referrer} referred {self.referred}"


class OrderStatusLog(models.Model):
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="status_logs")
    status = models.CharField(max_length=200)
    note = models.CharField(max_length=300, null=True, blank=True)
    updated_by = models.CharField(max_length=50, default="system", help_text="system, customer, vendor, admin")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"ORDER_{self.order.id}: {self.status}"


class Cart(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart: {self.id}"


ORDER_STATUS = (
    ("Order Received", "Order Received"),
    ("Order Processing", "Order Processing"),
    ("On the way", "On the way"),
    ("Order Completed", "Order Completed"),
    ("Order Cancelled", "Order Cancelled"),
)

METHOD = (
    ("Cash On Delivery", "Cash On Delivery"),
    ("Khalti", "Khalti"),
)

REFUND_STATUS = (
    ("no_refund", "No Refund"),
    ("pending", "Refund Pending"),
    ("processed", "Refund Processed"),
)


class CartProduct(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rate = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    subtotal = models.PositiveIntegerField()
    vendor_status = models.CharField(
        max_length=200, choices=ORDER_STATUS, default="Order Received",
        help_text="Per-item status managed by the vendor",
    )

    def __str__(self):
        return f"Cart {self.cart.id} - {self.product.title} x{self.quantity}"


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=10, choices=(("percent", "Percentage"), ("fixed", "Fixed Amount")))
    discount_value = models.PositiveIntegerField(help_text="Percentage or fixed amount off")
    min_order_amount = models.PositiveIntegerField(default=0, help_text="Minimum order total to apply")
    max_uses = models.PositiveIntegerField(default=100)
    used_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    is_referral = models.BooleanField(default=False, help_text="This coupon was generated for a referral")
    created_by = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, help_text="Customer who owns this referral coupon")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True, help_text="Vendor who created this coupon")
    is_approved = models.BooleanField(default=True, help_text="Admin must approve vendor-created coupons")

    def __str__(self):
        return self.code

    def is_valid(self):
        now = timezone.now()
        return self.is_active and self.used_count < self.max_uses and self.valid_from <= now <= self.valid_until


class Favorite(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("customer", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} - {self.product}"


class Order(models.Model):
    cart = models.OneToOneField(Cart, on_delete=models.CASCADE)
    ordered_by = models.CharField(max_length=200)
    shipping_address = models.CharField(max_length=200)
    mobile = models.CharField(max_length=20)
    email = models.EmailField(null=True, blank=True)
    subtotal = models.PositiveIntegerField()

    discount = models.PositiveIntegerField()
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)

    total = models.PositiveIntegerField()
    order_status = models.CharField(max_length=200, choices=ORDER_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, choices=METHOD, default="Cash On Delivery")
    payment_completed = models.BooleanField(default=False, null=True, blank=True)

    delivery_zone = models.ForeignKey(DeliveryZone, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_fee = models.PositiveIntegerField(default=0)

    cancellation_requested = models.BooleanField(default=False)
    cancellation_reason = models.TextField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    refund_status = models.CharField(max_length=20, choices=REFUND_STATUS, default="no_refund")
    refund_amount = models.PositiveIntegerField(default=0)

    platform_commission = models.PositiveIntegerField(default=0, help_text="Platform commission deducted from this order")
    special_instructions = models.TextField(null=True, blank=True, help_text="Customer instructions for this order")

    def __str__(self):
        return "Order: " + str(self.id)


class CommissionConfig(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, null=True, blank=True, help_text="Leave empty for global default")
    commission_type = models.CharField(max_length=10, choices=(("percent", "Percentage"), ("fixed", "Fixed per order")))
    commission_value = models.PositiveIntegerField(help_text="Percentage or fixed amount in Rs.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Commission Config"
        verbose_name_plural = "Commission Configs"

    def __str__(self):
        target = self.vendor.name if self.vendor else "Global Default"
        unit = "%" if self.commission_type == "percent" else " Rs."
        return f"{target}: {self.commission_value}{unit}"


PAYOUT_STATUS = (
    ("pending", "Pending"),
    ("paid", "Paid"),
)


class VendorPayout(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="payouts")
    amount = models.PositiveIntegerField(help_text="Payout amount in Rs.")
    period_start = models.DateField(help_text="Start of payout period")
    period_end = models.DateField(help_text="End of payout period")
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS, default="pending")
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vendor.name} — Rs. {self.amount} ({self.status})"
