from django.urls import path
from .views import *

app_name = 'ecomapp'
urlpatterns = [
    # Public pages
    path('', HomeView.as_view(), name='home'),
    path('about/', AboutView.as_view(), name='about'),
    path('contact/', ContactView.as_view(), name='contact'),
    path('products/', ProductsView.as_view(), name='products'),
    path('all-products/', AllProductsView.as_view(), name='allproducts'),
    path('kitchen/<slug:slug>/', VendorStorefrontView.as_view(), name='vendorstorefront'),
    path('product/<slug:slug>/', ProductDetailView.as_view(), name='productdetail'),
    path('search/', SearchView.as_view(), name='search'),
    path('forgot-password/', PasswordForgotView.as_view(), name='passwordforgot'),
    path('password-reset/<email>/<token>/', PasswordResetView.as_view(), name='passwordreset'),

    # Cart
    path('add-to-cart-<int:pro_id>/', AddToCartView.as_view(), name='addtocart'),
    path('my-cart/', MyCartView.as_view(), name='mycart'),
    path('manage-cart/<int:cp_id>/', ManageCartView.as_view(), name='managecart'),
    path('empty-cart/', EmptyCartView.as_view(), name='emptycart'),
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('validate-coupon/', ValidateCouponView.as_view(), name='validatecoupon'),
    path('delivery-zone-fee/', DeliveryZoneFeeView.as_view(), name='deliveryzonefee'),

    # Khalti payment
    path('khalti-request/', KhaltiRequestView.as_view(), name='khaltirequest'),
    path('khalti-verify', KhaltiVerifyView.as_view(), name='khaltiverify'),

    # Customer auth
    path('register/', CustomerRegistrationView.as_view(), name='customerregistration'),
    path('login/', CustomerLoginView.as_view(), name='customerlogin'),
    path('logout/', CustomerLogoutView.as_view(), name='customerlogout'),

    # Customer profile & orders
    path('profile/', CustomerProfileView.as_view(), name='customerprofile'),
    path('profile/order-<int:pk>/', CustomerOrderDetailView.as_view(), name='customerorderdetail'),
    path('track-order/<int:pk>/', TrackOrderView.as_view(), name='trackorder'),
    path('request-cancellation/<int:pk>/', RequestCancellationView.as_view(), name='requestcancellation'),
    path('order-confirmed/<int:pk>/', OrderConfirmedView.as_view(), name='orderconfirmed'),
    path('payment-failed/<int:pk>/', PaymentFailedView.as_view(), name='paymentfailed'),

    # Favorites / Wishlist
    path('toggle-favorite/<int:pro_id>/', ToggleFavoriteView.as_view(), name='togglefavorite'),
    path('remove-favorite/<int:pro_id>/', RemoveFavoriteView.as_view(), name='removefavorite'),
    path('favorites/', CustomerFavoriteListView.as_view(), name='favorites'),
    path('empty-favorites/', ClearFavoritesView.as_view(), name='emptyfavorites'),

    # Address management
    path('addresses/', CustomerAddressesView.as_view(), name='addresses'),
    path('address/add/', AddressCreateView.as_view(), name='addresscreate'),
    path('address/<int:pk>/edit/', AddressUpdateView.as_view(), name='addressedit'),
    path('address/<int:pk>/delete/', AddressDeleteView.as_view(), name='addressdelete'),
    path('address/<int:pk>/set-default/', SetDefaultAddressView.as_view(), name='addresssetdefault'),

    # Reviews
    path('submit-review/<slug:slug>/', SubmitReviewView.as_view(), name='submitreview'),

    # Vendor auth
    path('vendor/login/', VendorLoginView.as_view(), name='vendorlogin'),
    path('vendor/logout/', VendorLogoutView.as_view(), name='vendorlogout'),
    path('vendor/register/', VendorRegistrationView.as_view(), name='vendorregister'),

    # Vendor dashboard
    path('vendor/dashboard/', VendorDashboardView.as_view(), name='vendordashboard'),

    # Vendor products
    path('vendor/products/', VendorProductListView.as_view(), name='vendorproducts'),
    path('vendor/product/add/', VendorProductCreateView.as_view(), name='vendorproductadd'),
    path('vendor/product/<int:pk>/edit/', VendorProductUpdateView.as_view(), name='vendorproductedit'),
    path('vendor/product/<int:pk>/image/add/', ProductImageAddView.as_view(), name='vendorproductimageadd'),
    path('vendor/product/image/<int:pk>/delete/', ProductImageDeleteView.as_view(), name='vendorproductimagedelete'),

    # Vendor orders
    path('vendor/orders/', VendorOrderListView.as_view(), name='vendororders'),
    path('vendor/order/<int:pk>/', VendorOrderDetailView.as_view(), name='vendororderdetail'),
    path('vendor/order/<int:pk>/status/', VendorOrderStatusUpdateView.as_view(), name='vendororderstatus'),
    path('vendor/order/<int:pk>/bulk/', VendorOrderBulkActionView.as_view(), name='vendororderbulk'),

    # Vendor coupons
    path('vendor/coupons/', VendorCouponListView.as_view(), name='vendorcoupons'),
    path('vendor/coupon/add/', VendorCouponCreateView.as_view(), name='vendorcouponadd'),
    path('vendor/coupon/<int:pk>/delete/', VendorCouponDeleteView.as_view(), name='vendorcoupondelet'),

    # Vendor settings
    path('vendor/profile/', VendorProfileView.as_view(), name='vendorprofile'),
    path('vendor/change-password/', VendorChangePasswordView.as_view(), name='vendorchangepassword'),
    path('vendor/payouts/', VendorPayoutListView.as_view(), name='vendorpayouts'),
    path('vendor/business-hours/', VendorBusinessHoursView.as_view(), name='vendorbusinesshours'),
    path('vendor/toggle-vacation/', VendorToggleVacationView.as_view(), name='vendortogglevacation'),
    path('vendor/sales-report/', VendorSalesReportView.as_view(), name='vendorsalesreport'),

    # Admin
    path('admin-login/', AdminLoginView.as_view(), name='adminlogin'),
    path('admin-home/', AdminHomeView.as_view(), name='adminhome'),
    path('admin-all-orders/', AdminOrderListView.as_view(), name='adminorderlist'),
    path('admin-order/<int:pk>/', AdminOrderDetailView.as_view(), name='adminorderdetail'),
    path('admin-oder-<int:pk>-change/', AdminOrderStatusChangeView.as_view(), name='adminorderstatuschange'),
    path('admin-product/list/', AdminProductListView.as_view(), name='adminproductlist'),
    path('admin-product/add/', AdminProductCreateView.as_view(), name='adminproductcreate'),
    path('admin-payouts/', AdminPayoutListView.as_view(), name='adminpayouts'),
    path('admin-payout/<int:pk>/mark-paid/', AdminMarkPayoutPaidView.as_view(), name='adminmarkpayoutpaid'),
]
