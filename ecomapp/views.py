import csv
import json
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.utils.text import slugify
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, F, Prefetch, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (CreateView, DetailView, FormView, ListView,
                                  TemplateView, UpdateView, View)

from .forms import (AddressForm, CancellationForm, CheckoutForm,
                    CustomerLoginForm, CustomerRegistrationForm,
                    PasswordForgotForm, PasswordResetForm, ProductForm,
                    ReviewForm, VendorChangePasswordForm, VendorLoginForm,
                    VendorProfileForm, VendorRegistrationForm)
from .models import (ORDER_STATUS, REFUND_STATUS, Address, Admin, Cart,
                     CartProduct, Category, CommissionConfig, Coupon,
                     Customer, DeliveryZone, Favorite, Order, OrderStatusLog,
                     Product, ProductImage, Review, Vendor, VendorBusinessHour,
                     VendorPayout)
from .tasks import send_mail_async
from .utils import password_reset_token


def calculate_order_commission(order):
    """Calculate platform commission for an order based on vendor configs."""
    total_commission = 0
    for cp in order.cart.cartproduct_set.select_related("product__vendor").all():
        vendor = cp.product.vendor
        if not vendor:
            continue
        config = CommissionConfig.objects.filter(
            Q(vendor=vendor) | Q(vendor__isnull=True, is_active=True)
        ).filter(is_active=True).order_by("-vendor").first()
        if not config:
            continue
        item_total = cp.subtotal
        if config.commission_type == "percent":
            total_commission += item_total * config.commission_value // 100
        else:
            total_commission += config.commission_value
    return total_commission


def log_order_status(order, status, updated_by="system", note=None):
    OrderStatusLog.objects.create(order=order, status=status, updated_by=updated_by, note=note)


def adjust_stock_for_order(order, decrement=True):
    """Decrement or restore stock for all products in an order."""
    for cp in order.cart.cartproduct_set.select_related("product").all():
        if decrement:
            Product.objects.filter(pk=cp.product_id, stock__gte=cp.quantity).update(
                stock=F("stock") - cp.quantity
            )
        else:
            Product.objects.filter(pk=cp.product_id).update(
                stock=F("stock") + cp.quantity
            )


def send_order_notifications(order):
    """Send order confirmation to customer, notification to admin, and alerts to vendors."""
    base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', settings.EMAIL_HOST_USER)

    customer_email = order.email
    if customer_email:
        subject = f"Order Confirmed - ORDER_{order.id} | BhokLagyao"
        message = (
            f"Hi {order.ordered_by},\n\n"
            f"Your order has been received!\n\n"
            f"Order ID: ORDER_{order.id}\n"
            f"Total: Rs. {order.total}\n"
            f"Payment: {order.payment_method}\n"
            f"Delivery: {order.shipping_address}\n\n"
            f"We'll start preparing your food soon.\n"
            f"Track your order: {base_url}/track-order/{order.id}/\n\n"
            f"Thank you for ordering with BhokLagyao!"
        )
        send_mail_async(subject, message, from_email, [customer_email])

    admin_emails = list(
        User.objects.filter(admin__isnull=False).values_list("email", flat=True)
    )
    if admin_emails:
        admin_subject = f"New Order - ORDER_{order.id} | BhokLagyao"
        admin_message = (
            f"New order received!\n\n"
            f"Order ID: ORDER_{order.id}\n"
            f"Customer: {order.ordered_by}\n"
            f"Phone: {order.mobile}\n"
            f"Total: Rs. {order.total}\n"
            f"Delivery Zone: {order.delivery_zone}\n"
            f"Payment: {order.payment_method}\n\n"
            f"View order: {base_url}/admin-order/{order.id}/\n"
        )
        send_mail_async(admin_subject, admin_message, from_email, admin_emails)

    # Notify each vendor with items in this order
    vendor_items = {}
    for cp in order.cart.cartproduct_set.select_related("product__vendor").all():
        vendor = cp.product.vendor
        if vendor and vendor.contact_email:
            vendor_items.setdefault(vendor, []).append(cp)

    for vendor, items in vendor_items.items():
        items_list = "\n".join(
            f"  - {cp.product.title} x{cp.quantity} (Rs. {cp.subtotal})"
            for cp in items
        )
        vendor_subject = f"New Order Received - ORDER_{order.id} | {vendor.name}"
        vendor_message = (
            f"Hi {vendor.name},\n\n"
            f"You have a new order!\n\n"
            f"Order ID: ORDER_{order.id}\n"
            f"Customer: {order.ordered_by}\n"
            f"Phone: {order.mobile}\n"
            f"Delivery: {order.shipping_address}\n\n"
            f"Your items in this order:\n{items_list}\n\n"
            f"Manage order: {base_url}/vendor/orders/{order.id}/\n"
            f"Dashboard: {base_url}/vendor/dashboard/\n\n"
            f"Please update the status once you start preparing."
        )
        send_mail_async(vendor_subject, vendor_message, from_email, [vendor.contact_email])


# Create your views here.


def handler404(request, exception):
    return render(request, "404.html", status=404)


def handler400(request, exception):
    return render(request, "400.html", status=400)


def handler403(request, exception):
    return render(request, "403.html", status=403)


def handler500(request):
    return render(request, "500.html", status=500)


class EcomMixin(object):
    """Attach a session cart to the authenticated customer when possible."""

    def dispatch(self, request, *args, **kwargs):
        cart_id = request.session.get("cart_id")
        if not cart_id:
            return super().dispatch(request, *args, **kwargs)

        try:
            cart_obj = Cart.objects.select_related("customer").get(id=cart_id)
        except Cart.DoesNotExist:
            request.session.pop("cart_id", None)
            return super().dispatch(request, *args, **kwargs)

        if request.user.is_authenticated and Customer.objects.filter(user=request.user).exists():
            customer = request.user.customer
            if cart_obj.customer_id != customer.id:
                cart_obj.customer = customer
                cart_obj.save(update_fields=["customer"])
        return super().dispatch(request, *args, **kwargs)


class HomeView(EcomMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        all_products = Product.objects.select_related("category").prefetch_related(
            "productimage_set"
        ).filter(
            is_hidden=False,
            is_available=True,
        ).filter(
            Q(available_from__isnull=True) | Q(available_from__lte=now),
            Q(available_until__isnull=True) | Q(available_until__gte=now),
        ).order_by("-id")
        # Pagination keeps the homepage fast by limiting records per page.
        paginator = Paginator(all_products, 8)
        page_number = self.request.GET.get("page")
        product_list = paginator.get_page(page_number)
        context['product_list'] = product_list

        return context


class AllProductsView(EcomMixin, TemplateView):
    template_name = 'allproducts.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        products_qs = Product.objects.select_related("category").filter(
            is_hidden=False,
            is_available=True,
        ).filter(
            Q(available_from__isnull=True) | Q(available_from__lte=now),
            Q(available_until__isnull=True) | Q(available_until__gte=now),
        ).order_by("-id")
        categories = Category.objects.prefetch_related(
            Prefetch("product_set", queryset=products_qs, to_attr="prefetched_products")
        ).order_by("title")
        context["categories"] = categories
        return context


class ProductsView(EcomMixin, TemplateView):
    template_name = 'products.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        products = Product.objects.select_related("category").filter(
            is_hidden=False,
        ).filter(
            Q(available_from__isnull=True) | Q(available_from__lte=now),
            Q(available_until__isnull=True) | Q(available_until__gte=now),
        )
        search = self.request.GET.get("q", "").strip()
        category_slug = self.request.GET.get("category", "").strip()
        vendor_slug = self.request.GET.get("vendor", "").strip()
        sort = self.request.GET.get("sort", "popular")

        if search:
            products = products.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(category__title__icontains=search)
            )
        if category_slug:
            products = products.filter(category__slug=category_slug)
        if vendor_slug:
            products = products.filter(vendor__slug=vendor_slug)

        if sort == "price-low":
            products = products.order_by("selling_price", "title")
        elif sort == "price-high":
            products = products.order_by("-selling_price", "title")
        elif sort == "new":
            products = products.order_by("-id")
        else:
            products = products.order_by("-view_count", "-id")

        context["products"] = products
        context["categories"] = Category.objects.order_by("title")
        context["vendors"] = Vendor.objects.filter(is_active=True)
        context["active_category"] = category_slug
        context["active_vendor"] = vendor_slug
        context["active_sort"] = sort
        context["active_query"] = search
        return context


class ProductDetailView(EcomMixin, TemplateView):
    template_name = 'productdetail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        url_slug = self.kwargs['slug']
        product = get_object_or_404(
            Product.objects.select_related("category").prefetch_related(
                "productimage_set"
            ),
            slug=url_slug,
        )
        context['product'] = product
        context['now'] = timezone.now()
        # Use an atomic F expression to avoid race conditions on view count.
        Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
        product.view_count += 1
        context["related_products"] = Product.objects.select_related("category").filter(
            category=product.category,
            is_hidden=False,
        ).exclude(pk=product.pk).order_by("-view_count", "-id")[:4]

        reviews = Review.objects.filter(product=product, is_approved=True).select_related("customer").order_by("-created_at")
        context["reviews"] = reviews
        context["avg_rating"] = product.average_rating
        context["review_count"] = product.review_count

        user_review = None
        if self.request.user.is_authenticated and Customer.objects.filter(user=self.request.user).exists():
            user_review = Review.objects.filter(customer=self.request.user.customer, product=product).first()
            context["user_fav_ids"] = list(
                Favorite.objects.filter(customer=self.request.user.customer).values_list("product_id", flat=True)
            )
        context["user_review"] = user_review
        context["review_form"] = ReviewForm(instance=user_review)
        return context


class AddToCartView(EcomMixin, View):
    def get(self, request, *args, **kwargs):
        return redirect("ecomapp:products")

    def post(self, request, *args, **kwargs):
        product_id = kwargs['pro_id']
        product_obj = get_object_or_404(Product, id=product_id)
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if not product_obj.is_available_for_purchase:
            msg = f"{product_obj.title} is currently not available."
            if is_ajax:
                return JsonResponse({"success": False, "message": msg})
            messages.warning(request, msg)
            return redirect("ecomapp:productdetail", slug=product_obj.slug)

        price = product_obj.selling_price

        with transaction.atomic():
            product_locked = Product.objects.select_for_update().get(id=product_obj.id)
            if product_locked.stock < 1:
                msg = f"{product_obj.title} is out of stock."
                if is_ajax:
                    return JsonResponse({"success": False, "message": msg})
                messages.warning(request, msg)
                return redirect("ecomapp:productdetail", slug=product_obj.slug)

            cart_id = request.session.get("cart_id")
            cart_obj = None
            if cart_id:
                try:
                    cart_obj = Cart.objects.select_for_update().get(id=cart_id)
                except Cart.DoesNotExist:
                    request.session.pop("cart_id", None)

            if cart_obj is None:
                cart_obj = Cart.objects.create(total=0)
                request.session['cart_id'] = cart_obj.id

            existing_cp = CartProduct.objects.select_for_update().filter(
                cart=cart_obj, product=product_obj
            ).first()
            requested_qty = (existing_cp.quantity + 1) if existing_cp else 1
            if requested_qty > product_locked.stock:
                msg = f"Only {product_locked.stock} available for {product_obj.title}."
                if is_ajax:
                    return JsonResponse({"success": False, "message": msg})
                messages.warning(request, msg)
                return redirect("ecomapp:productdetail", slug=product_obj.slug)

            cart_product, created = CartProduct.objects.select_for_update().get_or_create(
                cart=cart_obj,
                product=product_obj,
                defaults={
                    "rate": price,
                    "quantity": 1,
                    "subtotal": price,
                },
            )
            if not created:
                CartProduct.objects.filter(id=cart_product.id).update(
                    quantity=F("quantity") + 1,
                    subtotal=F("subtotal") + price,
                )
            Cart.objects.filter(id=cart_obj.id).update(total=F("total") + price)

        # Recalculate cart item count for AJAX response
        from django.db.models import Sum
        qs = CartProduct.objects.filter(cart=cart_obj)
        cart_count = qs.aggregate(total_qty=Sum("quantity"))["total_qty"] or 0

        msg = f"{product_obj.title} added to your cart."
        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": msg,
                "cart_count": cart_count,
            })
        messages.success(request, msg)
        return redirect("ecomapp:mycart")


class MyCartView(EcomMixin, TemplateView):
    template_name = 'mycart.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_id = self.request.session.get("cart_id", None)
        if cart_id:
            try:
                cart = Cart.objects.prefetch_related(
                    "cartproduct_set__product"
                ).get(id=cart_id)
            except Cart.DoesNotExist:
                self.request.session.pop("cart_id", None)
                cart = None
        else:
            cart = None

        context['cart'] = cart
        return context


class ManageCartView(EcomMixin, View):
    """Handle increment/decrement/remove operations for cart items."""

    def get(self, request, *args, **kwargs):
        return redirect("ecomapp:mycart")

    def post(self, request, *args, **kwargs):
        cp_id = self.kwargs['cp_id']
        action = request.POST.get('action')
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        with transaction.atomic():
            cp_obj = get_object_or_404(
                CartProduct.objects.select_for_update().select_related("cart", "product"), id=cp_id
            )
            cart_obj = cp_obj.cart
            removed = False
            if action == "inc":
                if cp_obj.quantity >= cp_obj.product.stock:
                    msg = f"Only {cp_obj.product.stock} available for {cp_obj.product.title}."
                    if is_ajax:
                        return JsonResponse({"error": msg})
                    messages.warning(request, msg)
                    return redirect("ecomapp:mycart")
                CartProduct.objects.filter(id=cp_obj.id).update(
                    quantity=F("quantity") + 1,
                    subtotal=F("subtotal") + cp_obj.rate,
                )
                Cart.objects.filter(id=cart_obj.id).update(total=F("total") + cp_obj.rate)
            elif action == "dcr":
                if cp_obj.quantity <= 1:
                    Cart.objects.filter(id=cart_obj.id).update(total=F("total") - cp_obj.rate)
                    cp_obj.delete()
                    removed = True
                else:
                    CartProduct.objects.filter(id=cp_obj.id).update(
                        quantity=F("quantity") - 1,
                        subtotal=F("subtotal") - cp_obj.rate,
                    )
                    Cart.objects.filter(id=cart_obj.id).update(total=F("total") - cp_obj.rate)
            elif action == "rmv":
                Cart.objects.filter(id=cart_obj.id).update(total=F("total") - cp_obj.subtotal)
                cp_obj.delete()
                removed = True

        if is_ajax:
            cart_obj.refresh_from_db()
            cart_count = CartProduct.objects.filter(cart=cart_obj).aggregate(s=Sum("quantity"))["s"] or 0
            data = {"message": "Cart updated"}
            if removed:
                remaining = CartProduct.objects.filter(cart=cart_obj).exists()
                data["removed"] = True
                data["empty"] = not remaining
            else:
                cp_obj.refresh_from_db()
                data["qty"] = cp_obj.quantity
                data["subtotal"] = cp_obj.subtotal
            data["total"] = cart_obj.total
            data["cart_count"] = cart_count
            return JsonResponse(data)

        messages.success(request, "Cart updated.")
        return redirect("ecomapp:mycart")


class EmptyCartView(EcomMixin, View):
    """Clear all items from the session cart."""

    def get(self, request, *args, **kwargs):
        return redirect("ecomapp:mycart")

    def post(self, request, *args, **kwargs):
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
        cart_id = request.session.get("cart_id", None)
        if cart_id:
            cart = get_object_or_404(Cart, id=cart_id)
            cart.cartproduct_set.all().delete()
            cart.total = 0
            cart.save(update_fields=["total"])
            if is_ajax:
                return JsonResponse({"success": True, "message": "Cart cleared."})
            messages.success(request, "Your cart has been cleared.")
        elif is_ajax:
            return JsonResponse({"success": True, "message": "Cart is already empty."})
        return redirect("ecomapp:mycart")


class CheckoutView(EcomMixin, CreateView):
    """Collect shipping info and create an Order from the session cart."""

    template_name = 'checkout.html'
    form_class = CheckoutForm

    def get_delivery_fee(self, cart_total, zone):
        if zone and cart_total >= zone.min_order_for_free_delivery:
            return 0
        return zone.fee if zone else 0

    # this disptch method is to check weather the user is login or not and he/she is customer or not
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Customer.objects.filter(user=request.user).exists():
            pass
        else:
            return redirect("/login/?next=/checkout/")

        cart_id = request.session.get("cart_id")
        has_items = CartProduct.objects.filter(cart_id=cart_id).exists() if cart_id else False
        if not has_items:
            messages.warning(request, "Add at least one product before checkout.")
            return redirect("ecomapp:products")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_id = self.request.session.get("cart_id", None)
        if cart_id:
            cart_obj = Cart.objects.prefetch_related("cartproduct_set__product").get(id=cart_id)
        else:
            cart_obj = None
        context['cart'] = cart_obj
        zone_id = self.request.POST.get("delivery_zone") if self.request.method == "POST" else None
        zone = DeliveryZone.objects.filter(id=zone_id).first() if zone_id else None
        if zone is None:
            zone = DeliveryZone.objects.filter(is_active=True).first()
        delivery_fee = self.get_delivery_fee(cart_obj.total, zone) if cart_obj else 0
        context["delivery_fee"] = delivery_fee
        context["grand_total"] = (
            cart_obj.total + delivery_fee if cart_obj else 0
        )
        context["delivery_zones"] = DeliveryZone.objects.filter(is_active=True)
        customer = self.request.user.customer
        context["addresses"] = Address.objects.filter(customer=customer).order_by("-is_default")
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        cart_id = self.request.session.get("cart_id")
        if cart_id:
            form.cart_id = cart_id
            cart_obj = Cart.objects.get(id=cart_id)
            form.cart_total = cart_obj.total
        return form

    def form_valid(self, form):
        cart_id = self.request.session.get("cart_id")
        if not cart_id:
            return redirect("ecomapp:home")

        cart_obj = Cart.objects.get(id=cart_id)

        # Validate stock before placing order
        for cp in cart_obj.cartproduct_set.select_related("product").all():
            if cp.quantity > cp.product.stock:
                messages.error(
                    self.request,
                    f"Sorry, only {cp.product.stock} unit(s) of {cp.product.title} are available. "
                    f"You requested {cp.quantity}. Please update your cart.",
                )
                return redirect("ecomapp:mycart")

        zone = form.cleaned_data.get("delivery_zone")
        delivery_fee = self.get_delivery_fee(cart_obj.total, zone)
        coupon = form.cleaned_data.get("coupon_code")
        discount = 0
        if coupon:
            if coupon.discount_type == "percent":
                discount = cart_obj.total * coupon.discount_value // 100
            else:
                discount = min(coupon.discount_value, cart_obj.total)
            Coupon.objects.filter(id=coupon.id).update(used_count=F("used_count") + 1)

        total = cart_obj.total + delivery_fee - discount
        form.instance.cart = cart_obj
        form.instance.subtotal = cart_obj.total
        form.instance.discount = discount
        form.instance.coupon = coupon
        form.instance.delivery_fee = delivery_fee
        form.instance.total = total
        form.instance.order_status = "Order Received"
        del self.request.session['cart_id']
        pm = form.cleaned_data.get("payment_method")
        order = form.save()
        order.platform_commission = calculate_order_commission(order)
        order.save(update_fields=["platform_commission"])
        log_order_status(order, "Order Received", "system")
        adjust_stock_for_order(order, decrement=True)
        send_order_notifications(order)
        if pm == "Khalti":
            return redirect(reverse("ecomapp:khaltirequest") + "?o_id=" + str(order.id))
        messages.success(self.request, "Your order has been placed successfully.")
        return redirect(reverse("ecomapp:orderconfirmed", kwargs={"pk": order.id}))


class DeliveryZoneFeeView(View):
    """Return delivery fee for a given zone as JSON."""

    def get(self, request, *args, **kwargs):
        zone_id = request.GET.get("zone_id")
        cart_id = request.session.get("cart_id")
        if not zone_id or not cart_id:
            return JsonResponse({"fee": 0, "total": 0, "grand_total": 0})
        zone = get_object_or_404(DeliveryZone, id=zone_id, is_active=True)
        cart = Cart.objects.filter(id=cart_id).first()
        if not cart:
            return JsonResponse({"fee": 0, "total": 0, "grand_total": 0})
        fee = 0 if cart.total >= zone.min_order_for_free_delivery else zone.fee
        return JsonResponse({
            "fee": fee,
            "total": cart.total,
            "grand_total": cart.total + fee,
            "zone_name": zone.name,
            "min_free": zone.min_order_for_free_delivery,
        })


class ValidateCouponView(View):
    """AJAX endpoint to validate a coupon code and return discount info."""

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code", "").strip()
        cart_id = request.session.get("cart_id")
        if not code:
            return JsonResponse({"valid": False, "error": "No coupon code provided."})
        try:
            coupon = Coupon.objects.get(code__iexact=code, is_active=True, is_approved=True)
        except Coupon.DoesNotExist:
            return JsonResponse({"valid": False, "error": "Invalid or expired coupon code."})
        if not coupon.is_valid():
            return JsonResponse({"valid": False, "error": "This coupon has expired or reached its usage limit."})

        cart_total = 0
        if cart_id:
            cart = Cart.objects.filter(id=cart_id).first()
            if cart:
                cart_total = cart.total

        if coupon.min_order_amount and cart_total < coupon.min_order_amount:
            return JsonResponse({"valid": False, "error": f"Minimum order of Rs. {coupon.min_order_amount} required."})

        if coupon.vendor:
            if cart_id:
                has_vendor_item = CartProduct.objects.filter(
                    cart_id=cart_id, product__vendor=coupon.vendor
                ).exists()
                if not has_vendor_item:
                    return JsonResponse({"valid": False, "error": "This coupon is not applicable to items in your cart."})

        if coupon.discount_type == "percent":
            discount = cart_total * coupon.discount_value // 100
        else:
            discount = min(coupon.discount_value, cart_total)

        return JsonResponse({
            "valid": True,
            "code": coupon.code,
            "discount": discount,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
        })


class KhaltiRequestView(View):
    def get(self, request, *args, **kwargs):
        o_id = request.GET.get("o_id")
        order = get_object_or_404(Order, id=o_id)
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return redirect("/login/")
        if order.cart.customer_id != request.user.customer.id:
            return redirect("ecomapp:customerprofile")
        context = {
            "order": order
        }
        return render(request, "khaltirequest.html", context)


class KhaltiVerifyView(View):
    def get(self, request, *args, **kwargs):
        token = request.GET.get("token")
        amount = request.GET.get("amount")
        o_id = request.GET.get("order_id")

        url = "https://khalti.com/api/v2/payment/verify/"
        payload = {
            "token": token,
            "amount": amount
        }
        headers = {
            "Authorization": "Key test_secret_key_f59e8b7d18b4499ca40f68195a846e9b"
        }

        order_obj = get_object_or_404(Order, id=o_id)
        # Use requests with a timeout so the view doesn't hang on network issues.
        try:
            response = requests.post(url, payload, headers=headers, timeout=10)
            resp_dict = response.json()
        except requests.RequestException:
            return JsonResponse({
                "success": False,
                "message": "Payment verification failed. Please try again.",
                "redirect_url": reverse("ecomapp:paymentfailed", kwargs={"pk": order_obj.id}),
            }, status=502)
        success = bool(resp_dict.get("idx"))
        if success:
            order_obj.payment_completed = True
            order_obj.save(update_fields=["payment_completed"])
        data = {
            "success": success,
            "redirect_url": reverse(
                "ecomapp:orderconfirmed" if success else "ecomapp:paymentfailed",
                kwargs={"pk": order_obj.id},
            ),
            "message": "Payment completed." if success else "Payment could not be verified.",
        }
        return JsonResponse(data)


class SubmitReviewView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return redirect("/login/")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, slug=kwargs["slug"])
        customer = request.user.customer
        try:
            review = Review.objects.get(customer=customer, product=product)
        except Review.DoesNotExist:
            review = None
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            review = form.save(commit=False)
            review.customer = customer
            review.product = product
            review.is_approved = False
            review.save()
            messages.success(request, "Your review has been submitted and awaits approval.")
        else:
            messages.error(request, "Please fix the errors below.")
        return redirect("ecomapp:productdetail", slug=product.slug)


class CustomerAddressesView(EcomMixin, TemplateView):
    template_name = "address_list.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return redirect("/login/")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        context["addresses"] = Address.objects.filter(customer=customer)
        return context


class AddressCreateView(EcomMixin, CreateView):
    template_name = "address_form.html"
    form_class = AddressForm

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return redirect("/login/")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.customer = self.request.user.customer
        messages.success(self.request, "Address added successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("ecomapp:addresses")


class AddressUpdateView(EcomMixin, UpdateView):
    template_name = "address_form.html"
    form_class = AddressForm
    model = Address
    context_object_name = "address"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return redirect("/login/")
        addr = get_object_or_404(Address, pk=kwargs["pk"])
        if addr.customer_id != request.user.customer.id:
            return redirect("ecomapp:addresses")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.customer = self.request.user.customer
        messages.success(self.request, "Address updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("ecomapp:addresses")


class AddressDeleteView(EcomMixin, View):
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return JsonResponse({"error": "Unauthorized"}, status=403)
        addr = get_object_or_404(Address, pk=kwargs["pk"])
        if addr.customer_id != request.user.customer.id:
            return JsonResponse({"error": "Forbidden"}, status=403)
        addr.delete()
        messages.success(request, "Address deleted.")
        return redirect("ecomapp:addresses")


class SetDefaultAddressView(View):
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return JsonResponse({"error": "Unauthorized"}, status=403)
        addr = get_object_or_404(Address, pk=kwargs["pk"])
        if addr.customer_id != request.user.customer.id:
            return JsonResponse({"error": "Forbidden"}, status=403)
        Address.objects.filter(customer=addr.customer, is_default=True).update(is_default=False)
        addr.is_default = True
        addr.save(update_fields=["is_default"])
        return JsonResponse({"success": True})


# ─── Vendor Portal ────────────────────────────────────────────────

class VendorAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/vendor/login/")
        if not hasattr(request.user, "vendor"):
            return redirect("/vendor/login/")
        return super().dispatch(request, *args, **kwargs)


class VendorLoginView(FormView):
    template_name = "vendor/login.html"
    form_class = VendorLoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and hasattr(request.user, "vendor"):
            return redirect("ecomapp:vendordashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        user = authenticate(username=username, password=password)
        if user is not None and hasattr(user, "vendor"):
            if user.vendor.is_active:
                login(self.request, user)
                return redirect("ecomapp:vendordashboard")
            return render(self.request, self.template_name, {
                "form": self.form_class,
                "error": "Your kitchen is pending admin approval. Please wait for confirmation.",
            })
        return render(self.request, self.template_name, {"form": self.form_class, "error": "Invalid credentials or no vendor access."})

    def form_invalid(self, form):
        return render(self.request, self.template_name, {"form": form})


class VendorLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("ecomapp:vendorlogin")


class VendorRegistrationView(FormView):
    template_name = "vendor/register.html"
    form_class = VendorRegistrationForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and hasattr(request.user, "vendor"):
            return redirect("ecomapp:vendordashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            "Thanks! Your registration is pending admin approval. "
            "You'll be able to log in once approved.",
        )
        return redirect("ecomapp:vendorlogin")


class VendorDashboardView(VendorAccessMixin, TemplateView):
    template_name = "vendor/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor = self.request.user.vendor
        products = Product.objects.filter(vendor=vendor)

        # Orders containing this vendor's products
        vendor_product_ids = products.values_list("id", flat=True)
        vendor_cart_ids = CartProduct.objects.filter(product_id__in=vendor_product_ids).values_list("cart_id", flat=True).distinct()
        orders = Order.objects.filter(cart_id__in=vendor_cart_ids).order_by("-created_at")
        completed_orders = orders.filter(order_status="Order Completed")

        # Earnings calculation
        vendor_cp_ids = CartProduct.objects.filter(
            product_id__in=vendor_product_ids,
            cart_id__in=vendor_cart_ids,
        ).values_list("id", flat=True)

        gross_sales = CartProduct.objects.filter(
            id__in=vendor_cp_ids,
            cart__order__in=completed_orders,
        ).aggregate(s=Sum("subtotal"))["s"] or 0

        # Estimate commission on those sales
        config = CommissionConfig.objects.filter(
            Q(vendor=vendor) | Q(vendor__isnull=True, is_active=True)
        ).filter(is_active=True).order_by("-vendor").first()
        if config:
            if config.commission_type == "percent":
                total_commission = gross_sales * config.commission_value // 100
            else:
                total_commission = config.commission_value * completed_orders.count()
        else:
            total_commission = 0

        pending_payouts = VendorPayout.objects.filter(vendor=vendor, status="pending").aggregate(s=Sum("amount"))["s"] or 0

        # Low stock products
        low_stock_products = products.filter(stock__lte=F("low_stock_threshold"), is_hidden=False).order_by("stock")

        # Top selling products
        top_products = (
            CartProduct.objects.filter(product__in=products)
            .values("product__title", "product__id")
            .annotate(total_qty=Sum("quantity"))
            .order_by("-total_qty")[:5]
        )

        # Today's orders
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = orders.filter(created_at__gte=today_start)

        pending_count = orders.filter(order_status="Order Received").count()
        preparing_count = orders.filter(order_status="Preparing").count()

        # Status distribution
        status_counts = {}
        for st, label in ORDER_STATUS:
            status_counts[st] = orders.filter(order_status=st).count()

        # Recent reviews for vendor's products
        recent_reviews = Review.objects.filter(
            product__in=products, is_approved=True
        ).select_related("customer", "product").order_by("-created_at")[:5]

        context["vendor"] = vendor
        context["product_count"] = products.count()
        context["approved_products"] = products.filter(is_approved=True).count()
        context["pending_products"] = products.filter(is_approved=False).count()
        context["total_orders"] = orders.count()
        context["pending_orders"] = pending_count
        context["preparing_orders"] = preparing_count
        context["today_orders"] = today_orders.count()
        context["recent_orders"] = orders[:10]
        context["gross_sales"] = gross_sales
        context["total_commission"] = total_commission
        context["net_earnings"] = gross_sales - total_commission
        context["pending_payouts"] = pending_payouts
        context["low_stock_products"] = low_stock_products
        context["top_products"] = top_products
        context["status_counts"] = status_counts
        context["recent_reviews"] = recent_reviews
        return context


class VendorProductListView(VendorAccessMixin, ListView):
    template_name = "vendor/products.html"
    context_object_name = "products"

    def get_queryset(self):
        return Product.objects.filter(vendor=self.request.user.vendor).order_by("-id")


class VendorProductCreateView(VendorAccessMixin, CreateView):
    template_name = "vendor/product_form.html"
    form_class = ProductForm

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields.pop("vendor", None)
        form.fields.pop("slug", None)
        return form

    def form_valid(self, form):
        form.instance.vendor = self.request.user.vendor
        form.instance.slug = slugify(form.instance.title)
        messages.success(self.request, "Product added successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("ecomapp:vendorproducts")


class VendorProductUpdateView(VendorAccessMixin, UpdateView):
    template_name = "vendor/product_form.html"
    form_class = ProductForm
    model = Product

    def dispatch(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["pk"])
        if product.vendor_id != request.user.vendor.id:
            return redirect("ecomapp:vendorproducts")
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields.pop("vendor", None)
        form.fields.pop("slug", None)
        return form

    def form_valid(self, form):
        messages.success(self.request, "Product updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("ecomapp:vendorproducts")


class VendorOrderListView(VendorAccessMixin, ListView):
    template_name = "vendor/orders.html"
    context_object_name = "orders"

    def get_queryset(self):
        vendor = self.request.user.vendor
        vendor_product_ids = Product.objects.filter(vendor=vendor).values_list("id", flat=True)
        cart_ids = CartProduct.objects.filter(product_id__in=vendor_product_ids).values_list("cart_id", flat=True).distinct()
        qs = Order.objects.filter(cart_id__in=cart_ids).select_related("cart").order_by("-created_at")
        status_filter = self.request.GET.get("status")
        if status_filter:
            qs = qs.filter(order_status=status_filter)
        return qs


class VendorOrderDetailView(VendorAccessMixin, DetailView):
    template_name = "vendor/order_detail.html"
    model = Order
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor = self.request.user.vendor
        order = self.object
        line_items = order.cart.cartproduct_set.filter(product__vendor=vendor).select_related("product")
        context["line_items"] = line_items
        context["all_statuses"] = ORDER_STATUS

        items_subtotal = sum(cp.subtotal for cp in line_items) if line_items else 0
        context["items_subtotal"] = items_subtotal
        context["item_count"] = line_items.count()

        all_accepted = all(cp.vendor_status == "Order Processing" for cp in line_items) if line_items else False
        all_cancelled = all(cp.vendor_status == "Order Cancelled" for cp in line_items) if line_items else False
        has_pending = any(cp.vendor_status == "Order Received" for cp in line_items) if line_items else False
        context["all_accepted"] = all_accepted
        context["all_cancelled"] = all_cancelled
        context["has_pending"] = has_pending

        # Status label mapping for display
        context["status_labels"] = dict(ORDER_STATUS)

        return context


class VendorOrderStatusUpdateView(VendorAccessMixin, View):
    def post(self, request, *args, **kwargs):
        vendor = request.user.vendor
        cp_id = request.POST.get("cp_id")
        new_status = request.POST.get("status")
        if not cp_id or not new_status:
            return JsonResponse({"error": "Missing parameters."}, status=400)
        cp = get_object_or_404(CartProduct, pk=cp_id, product__vendor=vendor)
        valid_statuses = [s[0] for s in ORDER_STATUS]
        if new_status not in valid_statuses:
            return JsonResponse({"error": "Invalid status."}, status=400)

        old_status = cp.vendor_status
        cp.vendor_status = new_status
        cp.save(update_fields=["vendor_status"])

        # Auto-decrement stock when accepting, restore when cancelling
        if new_status == "Order Processing" and old_status != "Order Processing":
            Product.objects.filter(pk=cp.product_id, stock__gte=cp.quantity).update(
                stock=F("stock") - cp.quantity
            )
        elif new_status == "Order Cancelled" and old_status != "Order Cancelled":
            Product.objects.filter(pk=cp.product_id).update(
                stock=F("stock") + cp.quantity
            )

        return JsonResponse({"success": True, "status": new_status})


class VendorOrderBulkActionView(VendorAccessMixin, View):
    """Accept or reject all vendor items in an order at once."""

    def post(self, request, *args, **kwargs):
        vendor = request.user.vendor
        order = get_object_or_404(Order, pk=kwargs["pk"])
        action = request.POST.get("action")
        if action not in ("accept", "reject"):
            messages.error(request, "Invalid action.")
            return redirect("ecomapp:vendororderdetail", pk=order.pk)

        line_items = order.cart.cartproduct_set.filter(product__vendor=vendor).select_related("product")
        new_status = "Order Processing" if action == "accept" else "Order Cancelled"

        for cp in line_items:
            old_status = cp.vendor_status
            if cp.vendor_status == new_status:
                continue
            cp.vendor_status = new_status
            cp.save(update_fields=["vendor_status"])

            if action == "accept":
                Product.objects.filter(pk=cp.product_id, stock__gte=cp.quantity).update(
                    stock=F("stock") - cp.quantity
                )
            else:
                Product.objects.filter(pk=cp.product_id).update(
                    stock=F("stock") + cp.quantity
                )

        if action == "accept":
            messages.success(request, "All items accepted and stock updated.")
        else:
            messages.success(request, "All items cancelled and stock restored.")

        return redirect("ecomapp:vendororderdetail", pk=order.pk)


class VendorCouponListView(VendorAccessMixin, ListView):
    template_name = "vendor/coupons.html"
    context_object_name = "coupons"

    def get_queryset(self):
        return Coupon.objects.filter(vendor=self.request.user.vendor).order_by("-valid_from")


class VendorCouponCreateView(VendorAccessMixin, CreateView):
    template_name = "vendor/coupon_form.html"
    model = Coupon
    fields = ["code", "discount_type", "discount_value", "min_order_amount", "max_uses", "valid_from", "valid_until"]

    def form_valid(self, form):
        form.instance.vendor = self.request.user.vendor
        form.instance.is_approved = False
        form.instance.is_active = False
        messages.success(self.request, "Coupon created and sent for admin approval.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("ecomapp:vendorcoupons")


class VendorCouponDeleteView(VendorAccessMixin, View):
    def post(self, request, *args, **kwargs):
        coupon = get_object_or_404(Coupon, pk=kwargs["pk"], vendor=request.user.vendor)
        coupon.delete()
        messages.success(request, "Coupon deleted.")
        return redirect("ecomapp:vendorcoupons")


class VendorProfileView(VendorAccessMixin, UpdateView):
    template_name = "vendor/profile.html"
    form_class = VendorProfileForm

    def get_object(self, queryset=None):
        return self.request.user.vendor

    def form_valid(self, form):
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("ecomapp:vendorprofile")


class VendorChangePasswordView(VendorAccessMixin, FormView):
    template_name = "vendor/change_password.html"
    form_class = VendorChangePasswordForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        user = self.request.user
        user.set_password(form.cleaned_data["new_password"])
        user.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Password changed successfully.")
        return redirect("ecomapp:vendordashboard")


class VendorPayoutListView(VendorAccessMixin, ListView):
    template_name = "vendor/payouts.html"
    context_object_name = "payouts"

    def get_queryset(self):
        return VendorPayout.objects.filter(vendor=self.request.user.vendor).order_by("-created_at")


class ProductImageDeleteView(VendorAccessMixin, View):
    def post(self, request, *args, **kwargs):
        img = get_object_or_404(ProductImage, pk=kwargs["pk"], product__vendor=request.user.vendor)
        product_id = img.product_id
        img.delete()
        messages.success(request, "Image deleted.")
        return redirect("ecomapp:vendorproductedit", pk=product_id)


class ProductImageAddView(VendorAccessMixin, View):
    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, pk=kwargs["pk"], vendor=request.user.vendor)
        images = request.FILES.getlist("images")
        for img in images:
            ProductImage.objects.create(product=product, image=img)
        messages.success(request, f"{len(images)} image(s) added.")
        return redirect("ecomapp:vendorproductedit", pk=product.id)


class VendorBusinessHoursView(VendorAccessMixin, UpdateView):
    template_name = "vendor/business_hours.html"
    model = Vendor
    fields = []

    def get_object(self, queryset=None):
        return self.request.user.vendor

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor = self.object
        hours = {}
        for h in vendor.business_hours.all():
            hours[h.day] = h
        hours_list = []
        for day_num, day_name in VendorBusinessHour.WEEKDAYS:
            hours_list.append((day_num, day_name, hours.get(day_num)))
        context["hours_list"] = hours_list
        context["weekdays"] = VendorBusinessHour.WEEKDAYS
        return context

    def post(self, request, *args, **kwargs):
        vendor = self.get_object()
        for day, _ in VendorBusinessHour.WEEKDAYS:
            is_closed = request.POST.get(f"closed_{day}") == "on"
            open_time = request.POST.get(f"open_{day}") or None
            close_time = request.POST.get(f"close_{day}") or None
            VendorBusinessHour.objects.update_or_create(
                vendor=vendor, day=day,
                defaults={"open_time": open_time, "close_time": close_time, "is_closed": is_closed},
            )
        messages.success(request, "Business hours saved.")
        return redirect("ecomapp:vendorbusinesshours")


class VendorToggleVacationView(VendorAccessMixin, View):
    def post(self, request, *args, **kwargs):
        vendor = request.user.vendor
        vendor.is_on_vacation = not vendor.is_on_vacation
        vendor.save(update_fields=["is_on_vacation"])
        status = "enabled" if vendor.is_on_vacation else "disabled"
        messages.success(request, f"Vacation mode {status}. Your products are now {'hidden' if vendor.is_on_vacation else 'visible'}.")
        return redirect("ecomapp:vendordashboard")


class VendorSalesReportView(VendorAccessMixin, View):
    def get(self, request, *args, **kwargs):
        vendor = request.user.vendor
        products = Product.objects.filter(vendor=vendor)
        vendor_product_ids = products.values_list("id", flat=True)
        vendor_cp_ids = CartProduct.objects.filter(product_id__in=vendor_product_ids).values_list("id", flat=True)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename=sales_report_{vendor.slug}.csv"
        writer = csv.writer(response)
        writer.writerow(["Order ID", "Date", "Product", "Qty", "Rate", "Subtotal", "Status"])

        cps = CartProduct.objects.filter(
            id__in=vendor_cp_ids,
            cart__order__isnull=False,
        ).select_related("product", "cart__order").order_by("-cart__order__created_at")

        for cp in cps:
            writer.writerow([
                f"ORDER_{cp.cart.order.id}",
                cp.cart.order.created_at.strftime("%Y-%m-%d %H:%M"),
                cp.product.title,
                cp.quantity,
                cp.rate,
                cp.subtotal,
                cp.vendor_status,
            ])
        return response


class CustomerOrderAccessMixin(EcomMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return redirect("/login/")
        order = get_object_or_404(Order.objects.select_related("cart__customer"), pk=kwargs["pk"])
        if order.cart.customer_id != request.user.customer.id:
            return redirect("ecomapp:customerprofile")
        return super().dispatch(request, *args, **kwargs)


class OrderConfirmedView(CustomerOrderAccessMixin, DetailView):
    template_name = "orderconfirmed.html"
    model = Order
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("cart").prefetch_related(
            "cart__cartproduct_set__product"
        )


class PaymentFailedView(CustomerOrderAccessMixin, DetailView):
    template_name = "paymentfailed.html"
    model = Order
    context_object_name = "order"


class TrackOrderView(CustomerOrderAccessMixin, DetailView):
    template_name = "trackorder.html"
    model = Order
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("cart").prefetch_related(
            "cart__cartproduct_set__product"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_logs"] = self.object.status_logs.all()
        context["line_items"] = self.object.cart.cartproduct_set.select_related("product__vendor").all()
        return context


class RequestCancellationView(CustomerOrderAccessMixin, FormView):
    """Allow customer to request order cancellation."""
    template_name = "requestcancellation.html"
    form_class = CancellationForm

    def get_success_url(self):
        return reverse("ecomapp:customerorderdetail", kwargs={"pk": self.kwargs["pk"]})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = get_object_or_404(
            Order.objects.select_related("cart").prefetch_related("cart__cartproduct_set__product"),
            pk=self.kwargs["pk"],
        )
        return context

    def form_valid(self, form):
        order = get_object_or_404(Order, pk=self.kwargs["pk"])
        if order.order_status in ("Order Completed", "Order Cancelled"):
            messages.error(self.request, "This order cannot be cancelled.")
            return redirect("ecomapp:customerorderdetail", pk=order.id)
        adjust_stock_for_order(order, decrement=False)
        order.cancellation_requested = True
        order.cancellation_reason = form.cleaned_data["reason"]
        order.cancelled_at = timezone.now()
        order.order_status = "Order Cancelled"
        if order.payment_completed:
            order.refund_status = "pending"
            order.refund_amount = order.total
        order.save(update_fields=[
            "cancellation_requested", "cancellation_reason", "cancelled_at",
            "order_status", "refund_status", "refund_amount",
        ])
        log_order_status(order, "Order Cancelled", "customer", note=form.cleaned_data["reason"])
        messages.success(self.request, "Your order has been cancelled.")
        return super().form_valid(form)


class ToggleFavoriteView(View):
    """Add or remove a product from the customer's favorites."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": "Login required"}, status=401)
            return redirect("/login/")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=kwargs["pro_id"])
        customer = request.user.customer
        fav, created = Favorite.objects.get_or_create(customer=customer, product=product)
        if not created:
            fav.delete()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"favorited": False, "message": "Removed from favorites"})
            messages.success(request, f"Removed {product.title} from favorites.")
        else:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"favorited": True, "message": "Added to favorites"})
            messages.success(request, f"Added {product.title} to favorites.")
        return redirect(request.META.get("HTTP_REFERER", "/"))


class RemoveFavoriteView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return JsonResponse({"error": "Login required"}, status=401)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=kwargs["pro_id"])
        customer = request.user.customer
        deleted, _ = Favorite.objects.filter(customer=customer, product=product).delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"removed": bool(deleted), "message": "Removed from favorites"})
        if deleted:
            messages.success(request, f"Removed {product.title} from favorites.")
        else:
            messages.info(request, f"{product.title} was not in your favorites.")
        return redirect(request.META.get("HTTP_REFERER", "/"))


class CustomerFavoriteListView(TemplateView):
    template_name = "favorites.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Customer.objects.filter(user=request.user).exists():
            return super().dispatch(request, *args, **kwargs)
        return redirect("/login/?next=/favorites/")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["favorites"] = Favorite.objects.filter(
            customer=self.request.user.customer
        ).select_related("product__category")
        return context


class ClearFavoritesView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not Customer.objects.filter(user=request.user).exists():
            return JsonResponse({"error": "Login required"}, status=401)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        customer = request.user.customer
        count, _ = Favorite.objects.filter(customer=customer).delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"cleared": True, "count": count, "message": "All favorites cleared"})
        messages.success(request, f"Cleared {count} favorite(s).")
        return redirect("ecomapp:favorites")


class CustomerRegistrationView(CreateView):
    template_name = "customerregistration.html"
    form_class = CustomerRegistrationForm
    success_url = reverse_lazy("ecomapp:home")

    def form_valid(self, form):
        username = form.cleaned_data.get("username")
        password = form.cleaned_data.get("password")
        email = form.cleaned_data.get("email")
        user = User.objects.create_user(username, email, password)
        # one customer is one user
        form.instance.user = user
        login(self.request, user)
        return super().form_valid(form)

    def get_success_url(self):
        if "next" in self.request.GET:
            next_url = self.request.GET.get("next")
            return next_url
        else:
            return self.success_url


# logout logic
class CustomerLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("ecomapp:home")


class CustomerLoginView(FormView):
    """Login view restricted to Customer accounts."""

    template_name = "customerlogin.html"
    form_class = CustomerLoginForm
    success_url = reverse_lazy("ecomapp:home")

    # form valid method is a type of post method and is avialiable in create view formview and updateview
    def form_valid(self, form):
        uname = form.cleaned_data.get("username")
        pword = form.cleaned_data["password"]
        usr = authenticate(username=uname, password=pword)
        if usr is not None and Customer.objects.filter(user=usr).exists():
            login(self.request, usr)
        else:
            return render(self.request, self.template_name, {"form": self.form_class, "error": "Invalid Credentials"})
        return super().form_valid(form)

    def get_success_url(self):
        if "next" in self.request.GET:
            next_url = self.request.GET.get("next")
            return next_url
        else:
            return self.success_url


class AboutView(EcomMixin, TemplateView):
    template_name = 'about.html'


class ContactView(EcomMixin, TemplateView):
    template_name = 'contact.html'


class CustomerProfileView(TemplateView):
    """Display the current customer's profile and order history."""

    template_name = 'customerprofile.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Customer.objects.filter(user=request.user).exists():
            pass
        else:
            return redirect("/login/?next=/profile/")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.request.user.customer
        context['customer'] = customer
        orders = Order.objects.select_related("cart").filter(
            cart__customer=customer
        ).order_by("-id")
        context['orders'] = orders
        context['favorites_count'] = Favorite.objects.filter(customer=customer).count()
        context['reviews_count'] = Review.objects.filter(customer=customer).count()
        return context


class CustomerOrderDetailView(DetailView):
    template_name = 'customerorderdetail.html'
    model = Order
    context_object_name = "ord_obj"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Customer.objects.filter(user=request.user).exists():
            order_id = self.kwargs["pk"]
            order = Order.objects.select_related("cart__customer").get(id=order_id)
            if request.user.customer != order.cart.customer:
                return redirect("ecomapp:customerprofile")
        else:
            return redirect("/login/?next=/profile/")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("cart").prefetch_related(
            "cart__cartproduct_set__product"
        )


class AdminLoginView(FormView):
    """Login view restricted to Admin accounts."""

    template_name = "adminpages/adminlogin.html"
    form_class = CustomerLoginForm
    success_url = reverse_lazy("ecomapp:adminhome")

    def form_valid(self, form):
        uname = form.cleaned_data.get("username")
        pword = form.cleaned_data["password"]
        usr = authenticate(username=uname, password=pword)
        if usr is not None and Admin.objects.filter(user=usr).exists():
            login(self.request, usr)
        else:
            return render(self.request, self.template_name, {"form": self.form_class, "error": "Invalid Credentials"})
        return super().form_valid(form)



class PasswordForgotView(FormView):
    template_name = "forgotpassword.html"
    form_class = PasswordForgotForm
    success_url = "/forgot-password/?m=s"

    def form_valid(self, form):
        # get email from user
        email = form.cleaned_data.get("email")
        # get current host ip/domain
        host = self.request.META['HTTP_HOST']
        scheme = self.request.scheme
        # get customer and then user
        customer = Customer.objects.select_related("user").get(user__email=email)
        user = customer.user
        # send mail to the user with email
        text_content = 'Please Click the link below to reset your password. '
        reset_url = f"{scheme}://{host}/password-reset/{email}/{password_reset_token.make_token(user)}/"
        html_content = reset_url
        send_mail_async(
            'Password Reset Link | Django Ecommerce',
            text_content + html_content,
            settings.EMAIL_HOST_USER,
            [email],
        )
        return super().form_valid(form)


class PasswordResetView(FormView):
    template_name = "passwordreset.html"
    form_class = PasswordResetForm
    success_url = "/login/"

    def dispatch(self, request, *args, **kwargs):
        email = self.kwargs.get("email")
        user = User.objects.get(email=email)
        token = self.kwargs.get("token")
        if user is not None and password_reset_token.check_token(user, token):
            pass
        else:
            return redirect(reverse("ecomapp:passwordforgot") + "?m=e")

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        password = form.cleaned_data['new_password']
        email = self.kwargs.get("email")
        user = User.objects.get(email=email)
        user.set_password(password)
        user.save()
        return super().form_valid(form)




class AdminRequiredMixin(object):
    """Require an authenticated Admin user."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Admin.objects.filter(user=request.user).exists():
            pass
        else:
            return redirect("/admin-login/")
        return super().dispatch(request, *args, **kwargs)


class AdminPayoutListView(AdminRequiredMixin, ListView):
    template_name = "adminpages/adminpayouts.html"
    queryset = VendorPayout.objects.select_related("vendor").all()
    context_object_name = "payouts"


class AdminMarkPayoutPaidView(AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        payout = get_object_or_404(VendorPayout, pk=kwargs["pk"])
        payout.status = "paid"
        payout.paid_at = timezone.now()
        payout.save(update_fields=["status", "paid_at"])
        messages.success(request, f"Payout of Rs. {payout.amount} to {payout.vendor.name} marked as paid.")
        return redirect("ecomapp:adminpayouts")


class ProcessRefundView(AdminRequiredMixin, View):
    """Admin marks a refund as processed."""

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, pk=kwargs["pk"])
        if order.refund_status == "pending":
            adjust_stock_for_order(order, decrement=False)
            order.refund_status = "processed"
            order.save(update_fields=["refund_status"])
            messages.success(request, f"Refund for ORDER_{order.id} marked as processed.")
        return redirect("ecomapp:adminorderdetail", pk=order.id)


class AdminHomeView(AdminRequiredMixin, TemplateView):
    template_name = "adminpages/adminhome.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today_start - timezone.timedelta(days=6)

        completed_orders = Order.objects.filter(order_status="Order Completed")
        total_revenue = completed_orders.aggregate(s=Sum("total"))["s"] or 0
        total_orders = Order.objects.count()
        pending_count = Order.objects.filter(order_status="Order Received").count()
        processing_count = Order.objects.filter(order_status="Order Processing").count()
        todays_orders = Order.objects.filter(created_at__gte=today_start)
        todays_revenue = todays_orders.filter(order_status="Order Completed").aggregate(
            s=Sum("total")
        )["s"] or 0
        todays_count = todays_orders.count()

        total_customers = Customer.objects.count()
        total_vendors = Vendor.objects.count()
        pending_vendors = Vendor.objects.filter(is_approved=False).count()
        pending_products = Product.objects.filter(is_approved=False).count()
        low_stock_products = Product.objects.filter(stock__gt=0, stock__lte=F("low_stock_threshold")).count()
        out_of_stock = Product.objects.filter(stock=0).count()

        avg_order_value = completed_orders.aggregate(v=Avg("total"))["v"] or 0

        best_sellers = (
            CartProduct.objects.values("product__title", "product__id")
            .annotate(total_qty=Sum("quantity"))
            .filter(total_qty__gt=0)
            .order_by("-total_qty")[:5]
        )

        orders_by_status = {
            "Order Received": pending_count,
            "Order Processing": processing_count,
            "On the way": Order.objects.filter(order_status="On the way").count(),
            "Order Completed": completed_orders.count(),
            "Order Cancelled": Order.objects.filter(order_status="Order Cancelled").count(),
        }

        recent_orders = Order.objects.select_related("delivery_zone").order_by("-id")[:10]

        # Last 7 days revenue data for chart
        last_7_days = []
        for i in range(6, -1, -1):
            day = (today_start - timezone.timedelta(days=i))
            day_rev = Order.objects.filter(
                created_at__gte=day,
                created_at__lt=day + timezone.timedelta(days=1),
                order_status="Order Completed",
            ).aggregate(s=Sum("total"))["s"] or 0
            last_7_days.append({
                "date": day.strftime("%a"),
                "revenue": float(day_rev),
                "orders": Order.objects.filter(
                    created_at__gte=day,
                    created_at__lt=day + timezone.timedelta(days=1),
                ).count(),
            })

        # Top vendors by revenue
        top_vendors = (
            Vendor.objects.annotate(
                revenue=Sum("product__cartproduct__subtotal",
                           filter=Q(product__cartproduct__cart__order__isnull=False,
                                    product__cartproduct__cart__order__order_status="Order Completed"))
            )
            .filter(revenue__gt=0)
            .order_by("-revenue")[:5]
        )

        context.update({
            "today": now,
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "pending_count": pending_count,
            "todays_revenue": todays_revenue,
            "todays_count": todays_count,
            "total_customers": total_customers,
            "total_vendors": total_vendors,
            "pending_vendors": pending_vendors,
            "pending_products": pending_products,
            "low_stock_products": low_stock_products,
            "out_of_stock": out_of_stock,
            "avg_order_value": avg_order_value,
            "best_sellers": best_sellers,
            "orders_by_status": orders_by_status,
            "recent_orders": recent_orders,
            "chart_data": json.dumps(last_7_days),
            "orders_by_status_json": json.dumps(orders_by_status),
            "top_vendors": top_vendors,
        })
        return context


class AdminOrderDetailView(AdminRequiredMixin, DetailView):
    template_name = "adminpages/adminorderdetail.html"
    model = Order
    context_object_name = "ord_obj"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['allstatus'] = ORDER_STATUS
        return context

    def get_queryset(self):
        return super().get_queryset().select_related("cart").prefetch_related(
            "cart__cartproduct_set__product"
        )


class AdminOrderListView(AdminRequiredMixin, ListView):
    template_name = "adminpages/adminorderlist.html"
    queryset = Order.objects.all().order_by("-id")
    context_object_name = "allorders"


class AdminOrderStatusChangeView(AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        order_id = self.kwargs["pk"]
        order_obj = Order.objects.get(id=order_id)
        new_status = request.POST.get("status")
        cancelled = new_status == "Order Cancelled" and order_obj.order_status != "Order Cancelled"
        un_cancelled = order_obj.order_status == "Order Cancelled" and new_status != "Order Cancelled"
        if cancelled:
            adjust_stock_for_order(order_obj, decrement=False)
        elif un_cancelled:
            adjust_stock_for_order(order_obj, decrement=True)
        order_obj.order_status = new_status
        order_obj.save(update_fields=["order_status"])
        log_order_status(order_obj, new_status, "admin")
        return redirect(reverse_lazy("ecomapp:adminorderdetail", kwargs={"pk": order_id}))


class SearchView(TemplateView):
    template_name = "search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        srch = self.request.GET.get('search', '').strip()
        if srch:
            results = Product.objects.filter(
                Q(title__icontains=srch) | Q(description__icontains=srch),
                is_hidden=False,
            ).filter(
                Q(available_from__isnull=True) | Q(available_from__lte=now),
                Q(available_until__isnull=True) | Q(available_until__gte=now),
            ).select_related("category")
        else:
            results = Product.objects.none()
        context['results'] = results
        return context


class AdminProductListView(AdminRequiredMixin, ListView):
    template_name = "adminpages/adminproductlist.html"
    queryset = Product.objects.all().order_by("-id")
    context_object_name = "allproducts"


class AdminProductCreateView(AdminRequiredMixin, CreateView):
    template_name = "adminpages/adminproductcreate.html"
    form_class = ProductForm
    success_url = reverse_lazy("ecomapp:adminproductlist")

    #it is use to handle the multiples images form admin form
    def form_valid(self, form):
        p = form.save()
        images = self.request.FILES.getlist("more_images")
        for i in images:
            ProductImage.objects.create(product=p, image=i)
        return super().form_valid(form)
