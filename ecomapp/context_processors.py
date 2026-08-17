from django.db.models import Count

from .models import Cart


def cart_summary(request):
    """Load the session cart in one query and prefetch its product data."""
    cart_id = request.session.get("cart_id")
    if not cart_id:
        return {"cart_item_count": 0, "cart_preview": None}

    try:
        cart = (
            Cart.objects.filter(id=cart_id)
            .annotate(item_count=Count("cartproduct", distinct=True))
            .prefetch_related("cartproduct_set__product")
            .get()
        )
    except Cart.DoesNotExist:
        request.session.pop("cart_id", None)
        return {"cart_item_count": 0, "cart_preview": None}

    return {
        "cart_item_count": cart.item_count,
        "cart_preview": cart,
    }
