from django.db.models import Sum

from .models import Cart, CartProduct


def cart_summary(request):
    cart_id = request.session.get("cart_id")
    if not cart_id:
        return {"cart_item_count": 0, "cart_preview": None}

    item_count = (
        CartProduct.objects.filter(cart_id=cart_id).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    try:
        cart = Cart.objects.prefetch_related("cartproduct_set__product").get(id=cart_id)
    except Cart.DoesNotExist:
        request.session.pop("cart_id", None)
        return {"cart_item_count": 0, "cart_preview": None}

    return {"cart_item_count": item_count, "cart_preview": cart}
