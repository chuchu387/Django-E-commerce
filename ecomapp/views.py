import csv
import json
import requests
from collections import OrderedDict
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
from django.http import HttpResponse, JsonResponse
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
