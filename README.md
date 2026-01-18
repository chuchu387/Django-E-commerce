# Django E-commerce (BhookLagyao)

A full-stack Django e-commerce storefront with cart management, checkout, order tracking, and an admin dashboard for product and order operations.

## ✨ Highlights

- **Product catalog** with categories, detail pages, and pagination.
- **Cart & checkout** flow with quantity management and order summaries.
- **Customer accounts** for registration, login, and order history.
- **Admin dashboard** to manage orders, products, and statuses.
- **Payment integration** scaffolded for Khalti (test key included).
- **Search** across product titles and descriptions.

## 🧱 Tech Stack

- **Backend**: Django 5
- **Database**: SQLite (default, easy local setup)
- **Frontend**: Django templates + static assets

## 📁 Project Structure

```
Django-E-commerce/
├── ecomapp/          # App models, views, urls, forms
├── ecomproject/      # Project settings and URLs
├── templates/        # HTML templates
├── static/           # Static assets (CSS, JS, images)
├── media/            # Uploaded media files
└── db.sqlite3        # Local database (dev)
```

## ✅ Quick Start

### 1) Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Apply migrations

```bash
python manage.py migrate
```

### 4) Create an admin user (optional but recommended)

```bash
python manage.py createsuperuser
```

### 5) Run the development server

```bash
python manage.py runserver
```

Visit the app at: **http://127.0.0.1:8000/**

## 🔐 Configuration

This project uses settings in `ecomproject/settings.py`.

### Email settings (password reset)
Update these values if you want password reset emails to work:

```python
EMAIL_HOST_USER = "yourmail@gmail.com"
EMAIL_HOST_PASSWORD = "yourpassword"
```

### Khalti payment
A test key is embedded in `ecomapp/views.py` for the demo payment flow. Replace it with your own key in production.

## 🔍 Key Routes

- `/` — Home (latest products)
- `/all-products/` — Product listing
- `/product/<slug>/` — Product detail
- `/my-cart/` — Cart view
- `/checkout/` — Checkout flow
- `/profile/` — Customer profile & orders
- `/admin-login/` — Admin login
- `/admin-home/` — Admin dashboard

## 🧪 Tests

No automated tests are currently configured.

## 📝 Notes

- Static files are served from `/static/` and media uploads from `/media/`.
- For production, update `DEBUG`, `ALLOWED_HOSTS`, and secrets.

---

Built with ❤️ using Django.
