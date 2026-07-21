from django import forms
from django.contrib.auth.models import User
from django.utils.text import slugify

from .models import Address, CartProduct, Coupon, Customer, DeliveryZone, Order, Product, Review, Vendor


class CheckoutForm(forms.ModelForm):
    """Collects checkout details for an order."""

    delivery_zone = forms.ModelChoiceField(
        queryset=DeliveryZone.objects.filter(is_active=True),
        empty_label="Select your delivery zone",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Delivery zone",
    )

    coupon_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter coupon code",
        }),
        label="Coupon code (optional)",
    )

    class Meta:
        model = Order
        fields = ["ordered_by", "shipping_address", "mobile", "email", "payment_method", "delivery_zone", "special_instructions"]
        labels = {
            "ordered_by": "Full name",
            "shipping_address": "Delivery address",
            "mobile": "Mobile number",
            "email": "Email address",
            "payment_method": "Payment method",
            "special_instructions": "Special instructions (optional)",
        }
        widgets = {
            "ordered_by": forms.TextInput(attrs={
                "placeholder": "Name of the person receiving the order",
                "autocomplete": "name",
            }),
            "shipping_address": forms.TextInput(attrs={
                "placeholder": "Street, area, landmark",
                "autocomplete": "street-address",
            }),
            "mobile": forms.TextInput(attrs={
                "placeholder": "98XXXXXXXX",
                "autocomplete": "tel",
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }),
            "special_instructions": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Any special requests? (e.g. extra spicy, no onions)",
            }),
        }
        widgets = {
            "ordered_by": forms.TextInput(attrs={
                "placeholder": "Name of the person receiving the order",
                "autocomplete": "name",
            }),
            "shipping_address": forms.TextInput(attrs={
                "placeholder": "Street, area, landmark",
                "autocomplete": "street-address",
            }),
            "mobile": forms.TextInput(attrs={
                "placeholder": "98XXXXXXXX",
                "autocomplete": "tel",
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }),
        }

    def clean_mobile(self):
        mobile = self.cleaned_data.get("mobile", "").strip()
        if not mobile.isdigit() or len(mobile) != 10:
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        return mobile

    def clean_coupon_code(self):
        code = self.cleaned_data.get("coupon_code", "").strip()
        if not code:
            return None
        try:
            coupon = Coupon.objects.get(code__iexact=code, is_active=True, is_approved=True)
        except Coupon.DoesNotExist:
            raise forms.ValidationError("Invalid or expired coupon code.")
        if not coupon.is_valid():
            raise forms.ValidationError("This coupon has expired or reached its usage limit.")
        cart_total = 0
        cart_id = None
        if hasattr(self, "cart_total"):
            cart_total = self.cart_total
        if coupon.min_order_amount and cart_total < coupon.min_order_amount:
            raise forms.ValidationError(f"Minimum order of Rs. {coupon.min_order_amount} required for this coupon.")
        # Check vendor-specific coupons
        if coupon.vendor:
            cart_id = getattr(self, "cart_id", None)
            if cart_id:
                has_vendor_item = CartProduct.objects.filter(
                    cart_id=cart_id,
                    product__vendor=coupon.vendor,
                ).exists()
                if not has_vendor_item:
                    raise forms.ValidationError("This coupon is not applicable to items in your cart.")
        return coupon


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["full_name", "mobile", "street_address", "city", "postal_code", "label", "delivery_zone", "is_default"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Recipient name"}),
            "mobile": forms.TextInput(attrs={"class": "form-control", "placeholder": "98XXXXXXXX"}),
            "street_address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street, area, landmark"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Postal code (optional)"}),
            "label": forms.Select(attrs={"class": "form-control"}, choices=[("Home", "Home"), ("Work", "Work"), ("Other", "Other")]),
            "delivery_zone": forms.Select(attrs={"class": "form-control"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "full_name": "Full name",
            "mobile": "Mobile number",
            "street_address": "Street address",
            "city": "City",
            "postal_code": "Postal code",
            "label": "Label",
            "delivery_zone": "Delivery zone",
            "is_default": "Set as default address",
        }

    def clean_mobile(self):
        mobile = self.cleaned_data.get("mobile", "").strip()
        if not mobile.isdigit() or len(mobile) not in (10, 11, 12):
            raise forms.ValidationError("Enter a valid mobile number.")
        return mobile


class CancellationForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Tell us why you're cancelling...",
        }),
        label="Reason for cancellation",
        max_length=500,
    )


class CustomerRegistrationForm(forms.ModelForm):
    """Registers a new customer profile with a linked User."""

    username = forms.CharField(widget=forms.TextInput())
    password = forms.CharField(widget=forms.PasswordInput())
    email = forms.CharField(widget=forms.EmailInput())

    class Meta:
        model = Customer
        fields = ["username", "password", "email", "full_name", "address"]

    def clean_username(self):
        uname = self.cleaned_data.get("username")
        if User.objects.filter(username=uname).exists():
            raise forms.ValidationError("Customer already exists with this username.")
        return uname


class CustomerLoginForm(forms.Form):
    """Simple login form for customer credentials."""

    username = forms.CharField(widget=forms.TextInput())
    password = forms.CharField(widget=forms.PasswordInput())


class ProductForm(forms.ModelForm):
    """Admin form to create products with optional extra images."""

    more_images = forms.FileField(required=False, widget=forms.FileInput(attrs={
        "class": "form-control"
    }))

    class Meta:
        model = Product
        fields = ["title", "slug", "category", "vendor", "image", "marked_price", "selling_price", "description", "return_policy", "stock", "is_available", "is_hidden", "available_from", "available_until"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter a Product"
            }),
            "slug": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter a unique slug",
            }),
            "category": forms.Select(attrs={
                "class": "form-control"
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "form-control"
            }),
            "marked_price": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter a selling price of a product"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "description of a product",
                "rows": 10
            }),
            "return_policy": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter a Product"
            }),
            "stock": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Current inventory count",
            }),
            "is_available": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "is_hidden": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "available_from": forms.DateTimeInput(attrs={
                "class": "form-control",
                "type": "datetime-local",
            }),
            "available_until": forms.DateTimeInput(attrs={
                "class": "form-control",
                "type": "datetime-local",
            })
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug")
        title = self.cleaned_data.get("title")
        slug = slugify(slug or title)
        if not slug:
            raise forms.ValidationError("Enter a valid product slug.")
        if Product.objects.filter(slug=slug).exists():
            raise forms.ValidationError("This slug is already used by another product.")
        return slug

    def clean(self):
        cleaned_data = super().clean()
        marked_price = cleaned_data.get("marked_price")
        selling_price = cleaned_data.get("selling_price")
        description = cleaned_data.get("description", "")
        if marked_price is not None and selling_price is not None:
            if selling_price > marked_price:
                self.add_error("selling_price", "Selling price cannot be greater than marked price.")
            if selling_price <= 0 or marked_price <= 0:
                raise forms.ValidationError("Product prices must be greater than zero.")
        if description and len(description.strip()) < 25:
            self.add_error("description", "Write at least 25 characters so customers understand the product.")
        return cleaned_data


class VendorLoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}))


class VendorRegistrationForm(forms.ModelForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Choose a username"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "your@email.com"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Create a password"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm password"}))

    class Meta:
        model = Vendor
        fields = ["name", "description", "contact_phone", "address"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Your kitchen/restaurant name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Tell us about your kitchen..."}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "98XXXXXXXX"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Kitchen location"}),
        }
        labels = {
            "name": "Kitchen name",
            "contact_phone": "Phone number",
            "address": "Kitchen address",
        }

    def clean_username(self):
        uname = self.cleaned_data.get("username")
        if User.objects.filter(username=uname).exists():
            raise forms.ValidationError("Username already taken.")
        return uname

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already registered.")
        return email

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        cpw = cleaned.get("confirm_password")
        if pw and cpw and pw != cpw:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        vendor = super().save(commit=False)
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
        )
        vendor.user = user
        base_slug = slugify(vendor.name)
        slug = base_slug
        counter = 1
        while Vendor.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        vendor.slug = slug
        vendor.contact_email = self.cleaned_data["email"]
        vendor.is_active = False
        if commit:
            vendor.save()
        return vendor


class PasswordForgotForm(forms.Form):
    """Collects the email used for password reset."""

    email = forms.CharField(widget=forms.EmailInput(attrs={
        "class": "form-control",
        "placeholder": "Enter the email used in customer account"
    }))

    def clean_email(self):
        e = self.cleaned_data.get("email")
        if Customer.objects.filter(user__email=e).exists():
            pass
        else:
            raise forms.ValidationError("customer with this account doesn't exist")
        return e


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "text"]
        widgets = {
            "rating": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 1,
                "max": 5,
                "placeholder": "Rate 1-5",
            }),
            "text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Share your experience with this dish...",
            }),
        }
        labels = {
            "rating": "Rating (1-5)",
            "text": "Review",
        }


class PasswordResetForm(forms.Form):
    """Collects and validates a new password."""

    new_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'autocomplete': 'new-password',
        'placeholder': 'Enter New Password',
    }), label="New Password")
    confirm_new_password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'autocomplete': 'new-password',
        'placeholder': 'Confirm New Password',
    }), label="Confirm New Password")

    def clean_confirm_new_password(self):
        new_password = self.cleaned_data.get("new_password")
        confirm_new_password = self.cleaned_data.get("confirm_new_password")
        if new_password != confirm_new_password:
            raise forms.ValidationError(
                "New Passwords did not match!")
        return confirm_new_password


class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "contact_email", "contact_phone", "address", "logo", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Kitchen name"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email for order notifications"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "98XXXXXXXX"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Kitchen location"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Tell us about your kitchen..."}),
        }
        labels = {
            "name": "Kitchen name",
            "contact_email": "Contact email",
            "contact_phone": "Phone number",
            "logo": "Logo image",
        }


class VendorChangePasswordForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Current password"}))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "New password"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm new password"}))

    def clean_old_password(self):
        pw = self.cleaned_data.get("old_password")
        if not self.user.check_password(pw):
            raise forms.ValidationError("Current password is incorrect.")
        return pw

    def clean(self):
        cleaned = super().clean()
        np = cleaned.get("new_password")
        cp = cleaned.get("confirm_password")
        if np and cp and np != cp:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned
