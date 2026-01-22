from django.contrib.auth.models import User
from django import forms

from .models import Customer, Order, Product


class CheckoutForm(forms.ModelForm):
    """Collects checkout details for an order."""

    class Meta:
        model = Order
        fields = ["ordered_by", "shipping_address", "mobile", "email", "payment_method"]


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
        fields = ["title", "slug", "category", "image", "marked_price", "selling_price", "description", "return_policy"]
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
            })
        }


class PasswordForgotForm(forms.Form):
    """Collects the email used for password reset."""

    email = forms.CharField(widget=forms.EmailInput(attrs={
        "class": "form-control",
        "placeholder": "Enter the email used in customer account"
    }))

    def clean_email(self):
        e = self.cleaned_data.get("email")
        # this checks customer whose user email is equal to the email
        if Customer.objects.filter(user__email=e).exists():
            pass
        else:
            raise forms.ValidationError("customer with this account doesn't exist")
        return e


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
