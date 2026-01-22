import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import (CreateView, DetailView, FormView, ListView,
                                  TemplateView, View)

from .forms import (CheckoutForm, CustomerLoginForm, CustomerRegistrationForm,
                    PasswordForgotForm, PasswordResetForm, ProductForm)
from .models import (ORDER_STATUS, Admin, Cart, CartProduct, Category, Customer,
                     Order, Product, ProductImage)
from .utils import password_reset_token


# Create your views here.


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
        all_products = Product.objects.select_related("category").prefetch_related(
            "productimage_set"
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
        context['allcategories'] = Category.objects.all()
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
        # Use an atomic F expression to avoid race conditions on view count.
        Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
        product.view_count += 1
        return context


class AddToCartView(EcomMixin, TemplateView):
    template_name = 'addtocart.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # get product form requested url
        product_id = self.kwargs['pro_id']

        # get product
        product_obj = get_object_or_404(Product, id=product_id)

        # check if cart exist i use session
        cart_id = self.request.session.get("cart_id", None)
        if cart_id:
            # if cart id exist we need to fetch that cart id
            cart_obj = Cart.objects.get(id=cart_id)
            this_product_in_cart = cart_obj.cartproduct_set.filter(product=product_obj)

            # items already exist in cart
            if this_product_in_cart.exists():
                cartproduct = this_product_in_cart.last()
                cartproduct.quantity += 1
                cartproduct.subtotal += product_obj.selling_price
                cartproduct.save(update_fields=["quantity", "subtotal"])
                cart_obj.total += product_obj.selling_price
                cart_obj.save(update_fields=["total"])

            # new item is added in cart
            else:
                CartProduct.objects.create(
                    cart=cart_obj,
                    product=product_obj,
                    rate=product_obj.selling_price,
                    quantity=1,
                    subtotal=product_obj.selling_price,
                )
                cart_obj.total += product_obj.selling_price
                cart_obj.save(update_fields=["total"])
        else:
            # id cart id doesn't exist in our session we need to create a new cart
            cart_obj = Cart.objects.create(total=0)
            # Store the cart id immediately so future cart actions reuse it.
            self.request.session['cart_id'] = cart_obj.id
            CartProduct.objects.create(
                cart=cart_obj,
                product=product_obj,
                rate=product_obj.selling_price,
                quantity=1,
                subtotal=product_obj.selling_price,
            )
            cart_obj.total += product_obj.selling_price
            cart_obj.save(update_fields=["total"])

        return context


class MyCartView(EcomMixin, TemplateView):
    template_name = 'mycart.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_id = self.request.session.get("cart_id", None)
        if cart_id:
            cart = Cart.objects.prefetch_related(
                "cartproduct_set__product"
            ).get(id=cart_id)
        else:
            cart = None

        context['cart'] = cart
        return context


class ManageCartView(EcomMixin, View):
    """Handle increment/decrement/remove operations for cart items."""

    def get(self, request, *args, **kwargs):
        cp_id = self.kwargs['cp_id']
        action = request.GET.get('action')
        cp_obj = CartProduct.objects.select_related("cart").get(id=cp_id)
        cart_obj = cp_obj.cart
        if action == "inc":
            cp_obj.quantity += 1
            cp_obj.subtotal += cp_obj.rate
            cp_obj.save(update_fields=["quantity", "subtotal"])
            cart_obj.total += cp_obj.rate
            cart_obj.save(update_fields=["total"])
        elif action == "dcr":
            cp_obj.quantity -= 1
            cp_obj.subtotal -= cp_obj.rate
            cp_obj.save(update_fields=["quantity", "subtotal"])
            cart_obj.total -= cp_obj.rate
            cart_obj.save(update_fields=["total"])
            if cp_obj.quantity == 0:
                cp_obj.delete()
        elif action == "rmv":
            cart_obj.total -= cp_obj.subtotal
            cart_obj.save(update_fields=["total"])
            cp_obj.delete()
        else:
            pass
        return redirect("ecomapp:mycart")


class EmptyCartView(EcomMixin, View):
    """Clear all items from the session cart."""

    def get(self, request, *args, **kwargs):
        cart_id = request.session.get("cart_id", None)
        if cart_id:
            cart = Cart.objects.get(id=cart_id)
            cart.cartproduct_set.all().delete()
            cart.total = 0
            cart.save(update_fields=["total"])
        return redirect("ecomapp:mycart")


class CheckoutView(EcomMixin, CreateView):
    """Collect shipping info and create an Order from the session cart."""

    template_name = 'checkout.html'
    form_class = CheckoutForm
    success_url = reverse_lazy("ecomapp:home")

    # this disptch method is to check weather the user is login or not and he/she is customer or not
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Customer.objects.filter(user=request.user).exists():
            pass
        else:
            return redirect("/login/?next=/checkout/")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_id = self.request.session.get("cart_id", None)
        if cart_id:
            cart_obj = Cart.objects.get(id=cart_id)
        else:
            cart_obj = None
        context['cart'] = cart_obj
        return context

    def form_valid(self, form):
        cart_id = self.request.session.get("cart_id")
        if cart_id:
            cart_obj = Cart.objects.get(id=cart_id)
            form.instance.cart = cart_obj
            form.instance.subtotal = cart_obj.total
            form.instance.discount = 0
            form.instance.total = cart_obj.total
            form.instance.order_status = "Order Received"
            del self.request.session['cart_id']
            pm = form.cleaned_data.get("payment_method")
            order = form.save()
            if pm == "Khalti":
                return redirect(reverse("ecomapp:khaltirequest") + "?o_id=" + str(order.id))
        else:
            return redirect("ecomapp:home")
        return super().form_valid(form)


class KhaltiRequestView(View):
    def get(self, request, *args, **kwargs):
        o_id = request.GET.get("o_id")
        order = Order.objects.get(id=o_id)
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

        order_obj = Order.objects.get(id=o_id)
        # Use requests with a timeout so the view doesn't hang on network issues.
        response = requests.post(url, payload, headers=headers, timeout=10)
        resp_dict = response.json()
        success = bool(resp_dict.get("idx"))
        if success:
            order_obj.payment_completed = True
            order_obj.save(update_fields=["payment_completed"])
        data = {
            "success": success
        }
        return JsonResponse(data)


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
            return render(self.request, self.template_name, {"form": self.form_class, "error": "Invalid Creadientials"})
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
            return render(self.request, self.template_name, {"form": self.form_class, "error": "Invalid Creadientials"})
        return super().form_valid(form)



class PasswordForgotView(FormView):
    template_name = "forgotpassword.html"
    form_class = PasswordForgotForm
    success_url = "/forgot-password/?m=s"

    def form_valid(self, form):
        # get email from user
        email = form.cleaned_data.get("email")
        # get current host ip/domain
        url = self.request.META['HTTP_HOST']
        # get customer and then user
        customer = Customer.objects.select_related("user").get(user__email=email)
        user = customer.user
        # send mail to the user with email
        text_content = 'Please Click the link below to reset your password. '
        html_content = url + "/password-reset/" + email + \
            "/" + password_reset_token.make_token(user) + "/"
        send_mail(
            'Password Reset Link | Django Ecommerce',
            text_content + html_content,
            settings.EMAIL_HOST_USER,
            [email],
            fail_silently=False,
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
            return redirect(reverse("ecomapp:passworforgot") + "?m=e")

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


class AdminHomeView(AdminRequiredMixin, TemplateView):
    template_name = "adminpages/adminhome.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pendingorders'] = Order.objects.filter(order_status="Order Received").order_by("-id")
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
    def post(self, request, *agrs, **kwargs):
        order_id = self.kwargs["pk"]
        order_obj = Order.objects.get(id=order_id)
        new_status = request.POST.get("status")
        order_obj.order_status = new_status
        order_obj.save(update_fields=["order_status"])
        return redirect(reverse_lazy("ecomapp:adminorderdetail", kwargs={"pk": order_id}))


class SearchView(TemplateView):
    template_name = "search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        srch = self.request.GET.get('search', '').strip()
        if srch:
            results = Product.objects.filter(
                Q(title__icontains=srch) | Q(description__icontains=srch)
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
